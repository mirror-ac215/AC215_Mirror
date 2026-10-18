"""Deterministic safety check (M3-07).

Runs on the patient's text BEFORE text emotion, fusion or the LLM. It is plain
rules (regular expressions), not a model: the same message always gives the
same answer and every rule can be reviewed line by line. The face signal is
never an input.

Three outcomes besides "no hit":
- crisis:  suicide, self-harm, or harming someone else. The gateway withholds
           the persona reply, streams a `crisis` event with 988 resources and
           records a review flag for the patient's clinician.
- medical: a request for medical advice (doses, mixing or stopping medication,
           a diagnosis). The gateway withholds the persona reply and streams a
           `medical` event pointing to the clinician or pharmacist. No flag.
- support: the in-between: the patient asks for a real person or an
           appointment, or says they can't cope. The gateway streams a
           `support` event first (a short note plus Book / Call / Talk-now
           actions from the clinic settings), then the persona reply continues.
           A routine (non-urgent) review flag is recorded.

Order: crisis, then medical, then support. "How many pills would it take to
overdose" is crisis, not medical. Rules lean towards firing: a false alarm shows 988 to
someone who didn't need it; a miss leaves someone in crisis with a chatbot.

Changing a rule: edit CRISIS_RULES / MEDICAL_RULES / CRISIS_EXCEPTIONS, add a
case to tests/safety_cases.yaml, and get the change reviewed. Never log the
message text: log the rule id only.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

SafetyKind = Literal["crisis", "medical", "support"]

# (rule id, pattern). Patterns run on normalised text (see normalise()).
CRISIS_RULES: list[tuple[str, str]] = [
    ("suicide-word", r"\bsuicid(e|al)\b"),
    ("kill-self", r"\bkill(ing)? (my ?self|me)\b"),
    ("end-life", r"\b(end|take|ending|taking) my (own )?life\b"),
    ("want-die", (r"\b((want|wanna|wish|going|plan(ning)?|ready) (to )?|wish i (could|would) (just )?)"
     r"(die|be dead)\b")),
    ("better-dead", r"\bbetter off (dead|without me)\b"),
    ("not-alive", r"\b(don't|do not|dont) want to (be alive|live|exist|wake up)\b"),
    ("no-reason-live", r"\b(no|nothing( left)?) (reason |point )?to live( for)?\b"),
    ("not-here", r"\b(won't|will not|wont) be (here|around) (much longer|anymore|tomorrow)\b"),
    ("self-harm", r"\b(self[- ]?harm(ing)?|cut(ting)? myself|hurt(ing)? myself|harm(ing)? myself)\b"),
    ("overdose", r"\b(overdos(e|ing)|od on)\b"),
    ("cant-go-on", r"\b(can't|cannot|cant|can not) go on( anymore| living| like this)?\b"),
    ("goodbye-note", r"\b(suicide|goodbye) (note|letter)\b"),
    ("harm-other", r"\b(kill|killing|stab|stabbing|shoot|shooting) (him|her|them|someone|somebody|people|my \w+)\b"),
    ("hurt-other", r"\b(want|going|gonna|plan(ning)?) to (hurt|harm) (him|her|them|someone|somebody|people)\b"),
]

# Common phrases that look like a crisis rule but are not. Each one is blanked
# out of the text before its own rule runs; the rest of the message is still checked.
CRISIS_EXCEPTIONS: dict[str, list[str]] = {
    "kill-self": [
        r"\b(is|are|was|were|'s|'re) killing me\b",  # "this commute is killing me"
        r"\b(will|would|'ll|'d|gonna|going to) kill me\b",  # "my mom is going to kill me"
        r"\bkilling me (with|softly)\b",
    ],
    "want-die": [r"\bdying to\b", r"\bdie (of|from) (laughing|embarrassment|boredom)\b"],
    "not-alive": [r"\bwant to live (in|with|near|at|there|here|like|on)\b"],
    "harm-other": [r"\bshoot(ing)? my shot\b"],
    "self-harm": [r"\bhurt myself (at the gym|playing \w+|running|lifting|skiing|cooking|moving)\b"],
}

# Words that make a question about medicine rather than everyday life.
MEDS = (
    r"(pills?|tablets?|meds|medication|medicine|mg|milligrams|antidepressants?|ssris?|"
    r"sertraline|zoloft|fluoxetine|prozac|escitalopram|lexapro|xanax|alprazolam|lithium|"
    r"ibuprofen|advil|tylenol|paracetamol|acetaminophen|melatonin|sleeping pills|adderall)"
)

MEDICAL_RULES: list[tuple[str, str]] = [
    ("dose", r"\b(how (much|many)|what dose|dosage|max(imum)? dose)\b.*\b" + MEDS + r"\b"),
    ("mix-meds", r"\b(can i|should i|is it (ok|okay|safe) to) (take|mix|combine|drink)\b.*\b"
     + MEDS + r"\b"),
    ("stop-meds", r"\b(stop|quit|come off|skip|double|increase|lower|reduce) (taking )?(my )?"
     r"(dose|" + MEDS[1:] + r"\b"),
    ("diagnose", (r"\b(do i have|diagnose me with|is this|could this be|am i) (an? )?"
     r"(depression|clinically depressed|bipolar|adhd|ocd|ptsd|an anxiety disorder|"
     r"anxiety disorder|schizophreni\w*|autis\w*|bpd|a personality disorder)\b")),
    ("prescribe", r"\b(what|which) (meds|medication|antidepressant|pills?) should i (take|try|be on)\b"),
]

# The in-between: not a crisis, but the patient needs a person, not only the persona.
SUPPORT_RULES: list[tuple[str, str]] = [
    ("real-person", r"\b(talk|speak|chat) (to|with) (a |an )?(real|actual|live) (person|human|someone|therapist)\b"),
    ("someone-to-talk", r"\b(need|want|wish i had) (someone|somebody|a person) to talk to\b"),
    ("see-clinician", (r"\b(see|talk to|speak to|call|reach|contact) (my|a) "
                       r"(therapist|counsel+or|psychologist|psychiatrist|clinician|doctor)\b")),
    ("appointment", (r"\b((make|book|schedule|get|need|want) (an |another |a )?(appointment|session)"
                     r"|(when|how) (is|can i get|do i get) (my |a )?(next )?(appointment|session))\b")),
    ("cant-cope", (r"\b(can't|cannot|cant|can not) (cope\b|(handle|take) (it|this|anything|much more)"
                   r"( anymore| any more)?(?=$| and | but | i | right now))")),
    ("overwhelmed", (r"\b(i'm|i am|i feel|i keep|my life is|everything is|everything's) "
                     r"(falling apart|breaking down|so overwhelmed|completely overwhelmed|at my breaking point)\b")),
    ("need-help", r"\bi (really )?need (help|support)\b(?! (with|for|on|to))"),
]

_COMPILED_CRISIS = [(rid, re.compile(p)) for rid, p in CRISIS_RULES]
_COMPILED_MEDICAL = [(rid, re.compile(p)) for rid, p in MEDICAL_RULES]
_COMPILED_SUPPORT = [(rid, re.compile(p)) for rid, p in SUPPORT_RULES]
_COMPILED_EXCEPTIONS = {
    rid: [re.compile(p) for p in patterns] for rid, patterns in CRISIS_EXCEPTIONS.items()
}

CRISIS_MESSAGE = (
    "It sounds like you're carrying something really painful right now, and you "
    "deserve support from a person. I can't help with this here, but trained "
    "counsellors are available any time, day or night."
)
CRISIS_RESOURCES = [
    {"name": "988 Suicide & Crisis Lifeline", "contact": "call or text 988"},
    {"name": "Emergency services", "contact": "call 911 if you are in immediate danger"},
]
MEDICAL_MESSAGE = (
    "That's a question about medicine or a diagnosis, and I can't give medical "
    "advice. Your clinician, doctor or pharmacist is the right person to ask. "
    "If it feels urgent, call your doctor's office or 911."
)
SUPPORT_MESSAGE = (
    "It sounds like a lot right now. I'm here to keep talking with you, and your "
    "clinician is the best person to help with this. You can reach them below. "
    "If you ever feel unsafe, call or text 988."
)


@dataclass(frozen=True)
class SafetyResult:
    kind: SafetyKind | None  # None = no hit, carry on to the LLM
    rule_id: str | None = None

    @property
    def hit(self) -> bool:
        return self.kind is not None


def normalise(text: str) -> str:
    """Lower-case, straight apostrophes, single spaces: 'I’m' and 'I'm' then match the same rule."""
    text = unicodedata.normalize("NFKC", text).lower()
    text = text.replace("’", "'").replace("‘", "'")
    text = re.sub(r"[^\w'\s-]", " ", text)  # punctuation becomes a space
    return re.sub(r"\s+", " ", text).strip()


def _crisis_rule(text: str) -> str | None:
    for rule_id, pattern in _COMPILED_CRISIS:
        # Blank out this rule's harmless phrases first, then look again. In
        # "I want to kill myself, this is killing me" only "is killing me" is
        # removed and "kill myself" still fires.
        masked = text
        for exception in _COMPILED_EXCEPTIONS.get(rule_id, []):
            masked = exception.sub(" ", masked)
        if pattern.search(masked):
            return rule_id
    return None


def check(message: str) -> SafetyResult:
    """Message in, crisis / medical / support / no hit out. Crisis always wins."""
    text = normalise(message)
    if rule_id := _crisis_rule(text):
        return SafetyResult("crisis", rule_id)
    for rule_id, pattern in _COMPILED_MEDICAL:
        if pattern.search(text):
            return SafetyResult("medical", rule_id)
    for rule_id, pattern in _COMPILED_SUPPORT:
        if pattern.search(text):
            return SafetyResult("support", rule_id)
    return SafetyResult(None)


def crisis_payload(review_flag_created: bool) -> dict:
    """CrisisPayload from docs/contracts/api-gateway.openapi.yaml."""
    return {
        "message": CRISIS_MESSAGE,
        "resources": CRISIS_RESOURCES,
        "review_flag_created": review_flag_created,
    }


def medical_payload() -> dict:
    """MedicalPayload from docs/contracts/api-gateway.openapi.yaml."""
    return {"message": MEDICAL_MESSAGE}


def support_payload(booking_url: str, phone: str, live_available: bool) -> dict:
    """SupportPayload from docs/contracts/api-gateway.openapi.yaml.

    Book and Call appear only when the clinic has configured them (we never
    invent contact details). Talk-now is always listed with its availability;
    the chat screen hides the button while `available` is false.
    """
    actions: list[dict] = []
    if booking_url:
        actions.append({"type": "schedule", "label": "Book an appointment", "url": booking_url})
    if phone:
        actions.append({"type": "call", "label": "Call the office", "contact": phone})
    actions.append({"type": "live", "label": "Talk to someone now", "available": live_available})
    return {"message": SUPPORT_MESSAGE, "actions": actions}
