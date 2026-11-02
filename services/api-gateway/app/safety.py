"""Deterministic safety check (M3-07).

Runs on the patient's text BEFORE text emotion, fusion or the LLM. It is plain
rules (regular expressions), not a model: the same message always gives the
same answer and every rule can be reviewed line by line. The face signal is
never an input.

One outcome besides "no hit":
- crisis: suicide, self-harm, or harming someone else. The gateway withholds
          the persona reply, streams a `crisis` event with 988 resources and
          records a review flag for the patient's clinician (in memory until
          M3-10 saves it to the database).

Rules lean towards firing: a false alarm shows 988 to someone who didn't need
it; a miss leaves someone in crisis with a chatbot.

Changing a rule: edit CRISIS_RULES / CRISIS_EXCEPTIONS, add a
case to tests/safety_cases.yaml, and get the change reviewed. Never log the
message text: log the rule id only.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

SafetyKind = Literal["crisis"]

# (rule id, pattern). Patterns run on normalised text (see normalise()).
CRISIS_RULES: list[tuple[str, str]] = [
    ("suicide-word", r"\bsuicid(e|al)\b"),
    ("kill-self", r"\bkill(ing)? (my ?self|me)\b"),
    ("end-life", r"\b(end|take|ending|taking) my (own )?life\b"),
    ("want-die", (r"\b((want|wanna|wish|going|plan(ning)?|ready) (to )?|wish i (could|would) (just )?)"
     r"(die|be dead)\b")),
    ("wish-dead", (r"\bwish (i was|i were|i'd been|i had been) dead\b"
                   r"|\bwish (i'd never been|i had never been|i was never|i were never) born\b")),
    ("better-dead", (r"\bbetter off (dead|without me|if i (was|were|wasn't|weren't|just|had)"
                     r"( \w+)? (gone|dead|here|around|alive|disappeared|died|never been born))\b")),
    ("not-alive", (r"\b(don't|do not|dont) want to (be alive|live|exist|wake up)\b"
                   r"|\b(want|wanna) to stop (existing|living|being alive)\b")),
    ("rather-dead", r"\b((i'd|i would) rather be dead|(might|may) as well be dead)\b"),
    ("not-worth-living", (r"\blife (isn't|is not|isnt|ain't) worth living\b"
                          # not "tired of living with roommates"
                          r"|\b(tired|sick) of (living|being alive)\b(?! (in|with|at|near|on|like|out of)\b)")),
    ("nobody-miss", (r"\b(nobody|no one|no-one) (would|will|'d)( even)? (miss me|notice|care) "
                     r"if i (died|was gone|were gone|disappeared|wasn't here|weren't here|wasn't around)\b")),
    ("never-wake", r"\b(sleep|go to sleep|fall asleep) and never wake up\b"),
    ("no-reason-live", r"\b(no|nothing( left)?) (reason |point )?to live( for)?\b"),
    ("point-living", (r"\bpoint (of|in) (living|being alive|going on|life anymore|being here)\b"
                      # not "the point of living in a city this expensive"
                      r"(?! (in|near|at|on) (a|an|the|this|that|my) (city|town|house|apartment|flat|"
                      r"place|country|state|area|neighbou?rhood|dorm|building|street|suburb)\b)")),
    ("not-here", r"\b(won't|will not|wont) be (here|around) (much longer|anymore|tomorrow)\b"),
    ("not-be-here", r"\b(don't|do not|dont) want to be (here|around) (anymore|any more|on this earth|in this world)\b"),
    ("end-it", (r"\b(end(ing)? it all|(want|wanna|going|gonna|plan(ning)?|ready|thinking about|"
                r"think about|about|be) (to )?end(ing)? (it|things|everything)\b"
                # not "end it with him", "end it on a good note", "end it here for today"
                r"(?! (with|between|off|early|on|at|here|now|for (today|now|the day|tonight|the night))\b))"
                r"|\b(want|wish|need) (it all|everything|my life) to (end|stop|be over)\b"
                # not "I need everything to end on time", "my life to stop being so busy"
                r"(?! (on|at|by|being|so|early|soon|before|after)\b)")),
    ("kms", r"\b(kms|unalive (my ?self|me))\b"),
    ("method", (r"\b(hang(ing)? my ?self|shoot(ing)? my ?self|slit(ting)? my (wrists?|throat)|"
                r"jump(ing)? (off|from) (a|the|my) (bridge|building|roof|"
                r"cliff|balcony|tower)|(in front of|under) (a|the) (train|bus|truck)|"
                r"(took|take|taking|swallowed|swallow(ing)?) (all|a bunch|a handful|the whole bottle) "
                r"(of )?(my |the )?(pills|meds|medication|tablets))\b")),
    ("self-harm", (r"\b(self[- ]?harm(ing)?|cut(ting)? myself|hurt(ing)? myself|harm(ing)? myself"
                   r"|cutting( myself)? again)\b")),
    ("overdose", r"\b(overdos(e|ing)|od on)\b"),
    ("cant-go-on", r"\b(can't|cannot|cant|can not) go on( anymore| living| like this)?\b"),
    ("goodbye-note", r"\b(suicide|goodbye) (note|letter)\b"),
    ("harm-other", r"\b(kill|killing|stab|stabbing|shoot|shooting) (him|her|them|someone|somebody|people|my \w+)\b"),
    ("hurt-other", r"\b(want|going|gonna|plan(ning)?) to (hurt|harm) (him|her|them|someone|somebody|people|my \w+)\b"),
]

# Common phrases that look like a crisis rule but are not. Each one is blanked
# out of the text before its own rule runs; the rest of the message is still checked.
CRISIS_EXCEPTIONS: dict[str, list[str]] = {
    "kill-self": [
        r"\b(is|are|was|were|'s|'re) killing me\b",  # "this commute is killing me"
        r"\b(will|would|'ll|'d|gonna|going to) kill me\b",  # "my mom is going to kill me"
        r"\bkilling me (with|softly)\b",
    ],
    "want-die": [
        r"\bdying to\b",
        r"\bdie (of|from) (laughing|embarrassment|boredom)\b",
        # "my phone is going to die", "laptop's about to die"
        (r"\b(phone|battery|laptop|computer|car|tablet|ipad|airpods|headphones)('s)?( is| are| was)?"
         r"( literally| probably| about)? (going to|gonna|about to) die\b"),
    ],
    "not-alive": [r"\bwant to live (in|with|near|at|there|here|like|on)\b"],
    "harm-other": [
        r"\bshoot(ing)? my shot\b",
        # "I'll shoot him a text", "shoot my boss an email"
        (r"\bshoot(ing)? (him|her|them|someone|somebody|my \w+) (a |an )?(quick )?"
         r"(text|message|email|e-mail|dm|note|line|msg)\b"),
        # "the kids are killing my vibe"
        r"\bkill(ing)? my (vibe|mood|buzz|battery|time|appetite|motivation|joy|plants?)\b",
    ],
    "method": [
        r"\bshoot(ing)? my ?self in the foot\b",  # "I'll shoot myself in the foot if I say yes"
        (r"\btook all my (pills|meds|medication) (on time|as prescribed|like (i was supposed to|"
         r"(my|the) doctor said))\b"),
    ],
    "hurt-other": [
        # "I'm going to hurt my back lifting that"
        (r"\b(hurt|harm) my (back|knee|knees|neck|shoulder|ankle|wrist|leg|arm|foot|feet|hand|head|"
         r"eyes|chances|grades?|career|reputation|credit)\b"),
    ],
    "self-harm": [r"\bhurt myself (at the gym|playing \w+|running|lifting|skiing|cooking|moving)\b"],
}

_COMPILED_CRISIS = [(rid, re.compile(p)) for rid, p in CRISIS_RULES]
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
    """Message in, crisis or no hit out."""
    if rule_id := _crisis_rule(normalise(message)):
        return SafetyResult("crisis", rule_id)
    return SafetyResult(None)


def crisis_payload(review_flag_created: bool) -> dict:
    """CrisisPayload from docs/contracts/api-gateway.openapi.yaml."""
    return {
        "message": CRISIS_MESSAGE,
        "resources": CRISIS_RESOURCES,
        "review_flag_created": review_flag_created,
    }

