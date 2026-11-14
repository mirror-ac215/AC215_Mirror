"""Deterministic safety check (M3-07).

Runs on the patient's text BEFORE text emotion, fusion or the LLM. It is plain
rules (regular expressions), not a model: the same message always gives the
same answer and every rule can be reviewed line by line. The face signal is
never an input.

Three outcomes besides "no hit", checked in this order (crisis -> medication -> camera):
- crisis: suicide, self-harm, or harming someone else. The gateway withholds
          the persona reply, streams a `crisis` event with 988 resources and
          records a review flag for the patient's clinician.
- medication: a question about changing, stopping, mixing or dosing
          medication (M3-09). The LLM is skipped and the patient gets
          MEDICATION_REPLY as an ordinary streamed reply, pointing them to
          their prescriber. No new event type, no contract change.
- camera: a question about what the camera sees or keeps (M3-24). The LLM is
          skipped and the patient gets CAMERA_REPLY as an ordinary streamed
          reply. Only asked when crisis and medication did not fire, so
          "can you see me? I want to die" is still a crisis.

Crisis rules lean towards firing: a false alarm shows 988 to someone who didn't
need it; a miss leaves someone in crisis with a chatbot. Crisis always wins: "how
many pills to overdose" is a crisis, not a dosing question.

Changing a rule: edit the rules / exceptions below, add a case to
tests/safety_cases.yaml, and get the change reviewed. Never log the message
text: log the rule id only.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

SafetyKind = Literal["crisis", "medication", "camera"]

_MEDS = (
    r"(meds|medication|medications|medicine|pills?|tablets?|antidepressants?|"
    r"dose|doses|dosage|prescription|sertraline|zoloft|fluoxetine|prozac|escitalopram|"
    r"lexapro|citalopram|paroxetine|paxil|venlafaxine|effexor|bupropion|wellbutrin|"
    r"lithium|quetiapine|seroquel|aripiprazole|abilify|lamotrigine|lamictal|trazodone|"
    r"mirtazapine|alprazolam|xanax|lorazepam|ativan|clonazepam|klonopin|diazepam|valium|"
    r"zolpidem|ambien|adderall|ritalin|methylphenidate|propranolol|hydroxyzine|"
    r"insulin|birth control|the pill|melatonin|tylenol|acetaminophen|paracetamol|ibuprofen|"
    r"advil|aspirin|benadryl|gabapentin|metformin|levothyroxine|prednisone|steroids|"
    r"inhaler|painkillers?|sleeping pills?|sleep aids?|antipsychotics?|mood stabili[sz]ers?|"
    r"benzos?|opioids?|oxycodone|tramadol|suboxone|methadone|naltrexone)"
)

# (rule id, pattern). Patterns run on normalised text (see normalise()).
CRISIS_RULES: list[tuple[str, str]] = [
    ("suicide-word", r"\bsuicid(e|al)\b"),
    ("kill-self", r"\bkill(ing)? (my ?self|me)\b"),
    ("end-life", r"\b(end|take|ending|taking) my (own )?life\b"),
    (
        "want-die",
        (
            r"\b((want|wanna|wish|going|plan(ning)?|ready) (to )?|wish i (could|would) (just )?)"
            r"(die|be dead)\b"
        ),
    ),
    (
        "wish-dead",
        (
            r"\bwish (i was|i were|i'd been|i had been) dead\b"
            r"|\bwish (i'd never been|i had never been|i was never|i were never) born\b"
        ),
    ),
    (
        "better-dead",
        (
            r"\bbetter off (dead|without me|if i (was|were|wasn't|weren't|just|had)"
            r"( \w+)? (gone|dead|here|around|alive|disappeared|died|never been born))\b"
        ),
    ),
    (
        "not-alive",
        (
            r"\b(don't|do not|dont) want to (be alive|live|exist|wake up)\b"
            r"|\b(want|wanna) to stop (existing|living|being alive)\b"
        ),
    ),
    ("rather-dead", r"\b((i'd|i would) rather be dead|(might|may) as well be dead)\b"),
    (
        "not-worth-living",
        (
            r"\blife (isn't|is not|isnt|ain't) worth living\b"
            # not "tired of living with roommates"
            r"|\b(tired|sick) of (living|being alive)\b(?! (in|with|at|near|on|like|out of)\b)"
        ),
    ),
    (
        "nobody-miss",
        (
            r"\b(nobody|no one|no-one) (would|will|'d)( even)? (miss me|notice|care) "
            r"if i (died|was gone|were gone|disappeared|wasn't here|weren't here|wasn't around)\b"
        ),
    ),
    ("never-wake", r"\b(sleep|go to sleep|fall asleep) and never wake up\b"),
    ("no-reason-live", r"\b(no|nothing( left)?) (reason |point )?to live( for)?\b"),
    (
        "point-living",
        (
            r"\bpoint (of|in) (living|being alive|going on|life anymore|being here)\b"
            # not "the point of living in a city this expensive"
            r"(?! (in|near|at|on) (a|an|the|this|that|my) (city|town|house|apartment|flat|"
            r"place|country|state|area|neighbou?rhood|dorm|building|street|suburb)\b)"
        ),
    ),
    ("not-here", r"\b(won't|will not|wont) be (here|around) (much longer|anymore|tomorrow)\b"),
    (
        "not-be-here",
        r"\b(don't|do not|dont) want to be (here|around) (anymore|any more|on this earth|in this world)\b",
    ),
    (
        "end-it",
        (
            r"\b(end(ing)? it all|(want|wanna|going|gonna|plan(ning)?|ready|thinking about|"
            r"think about|about|be) (to )?end(ing)? (it|things|everything)\b"
            # not "end it with him", "end it on a good note", "end it here for today"
            r"(?! (with|between|off|early|on|at|here|now|for (today|now|the day|tonight|the night))\b))"
            r"|\b(want|wish|need) (it all|everything|my life) to (end|stop|be over)\b"
            # not "I need everything to end on time", "my life to stop being so busy"
            r"(?! (on|at|by|being|so|early|soon|before|after)\b)"
        ),
    ),
    ("kms", r"\b(kms|unalive (my ?self|me))\b"),
    (
        "method",
        (
            r"\b(hang(ing)? my ?self|shoot(ing)? my ?self|slit(ting)? my (wrists?|throat)|"
            r"jump(ing)? (off|from) (a|the|my) (bridge|building|roof|"
            r"cliff|balcony|tower)|(in front of|under) (a|the) (train|bus|truck)|"
            r"(took|take|taking|swallowed|swallow(ing)?) (all|a bunch|a handful|the whole bottle) "
            r"(of )?(my |the )?(pills|meds|medication|tablets))\b"
        ),
    ),
    (
        "self-harm",
        (
            r"\b(self[- ]?harm(ing)?|cut(ting)? myself|hurt(ing)? myself|harm(ing)? myself"
            r"|cutting( myself)? again)\b"
        ),
    ),
    ("overdose", r"\b(overdos(e|ing)|od on)\b"),
    # "what dose of xanax is lethal", "how many pills does it take to die" (M3-09 review)
    (
        "lethal-dose",
        (
            r"\b(lethal|fatal|deadly|toxic) (\w+ ){0,2}(dose|dosage|overdose|amount of "
            + _MEDS
            + r")\b"
            r"|\b(dose|dosage|amount) (of )?(\w+ ){0,3}(is |would be |be )?(lethal|fatal|deadly)\b"
            r"|\bhow (many|much)\b(\s\S+){0,8}\s(to die|not wake up|never wake up|to kill (me|my ?self)"
            r"|to be dead|to end it|be (lethal|fatal|deadly))\b"
        ),
    ),
    # "I took too many pills", "I just took 30 of my sleeping pills", "I took 20 xanax"
    (
        "took-too-many",
        (
            r"\b(took|taken|swallowed|had|taking|swallowing) (way )?(too (many|much)|\d{2,}|"
            r"(ten|twelve|fifteen|twenty|thirty|forty|fifty|a hundred))"
            r"( of)?( my| the)?( \w+){0,2} " + _MEDS + r"\b"
        ),
    ),
    ("cant-go-on", r"\b(can't|cannot|cant|can not) go on( anymore| living| like this)?\b"),
    ("goodbye-note", r"\b(suicide|goodbye) (note|letter)\b"),
    (
        "harm-other",
        r"\b(kill|killing|stab|stabbing|shoot|shooting) (him|her|them|someone|somebody|people|my \w+)\b",
    ),
    (
        "hurt-other",
        r"\b(want|going|gonna|plan(ning)?) to (hurt|harm) (him|her|them|someone|somebody|people|my \w+)\b",
    ),
]

# Common phrases that look like a crisis rule but are not. Each one is blanked
# out of the text before its own rule runs; the rest of the message is still checked.
CRISIS_EXCEPTIONS: dict[str, list[str]] = {
    # "a lethal dose of stress", "a deadly dose of reality"
    "lethal-dose": [
        (
            r"\b(lethal|fatal|deadly|toxic) (dose|amount) of (stress|reality|drama|boredom|cuteness|"
            r"sarcasm|caffeine|coffee|work|homework|nostalgia|cringe)\b"
        )
    ],
    "kill-self": [
        r"\b(is|are|was|were|'s|'re) killing me\b",  # "this commute is killing me"
        r"\b(will|would|'ll|'d|gonna|going to) kill me\b",  # "my mom is going to kill me"
        r"\bkilling me (with|softly)\b",
    ],
    "want-die": [
        r"\bdying to\b",
        r"\bdie (of|from) (laughing|embarrassment|boredom)\b",
        # "my phone is going to die", "laptop's about to die"
        (
            r"\b(phone|battery|laptop|computer|car|tablet|ipad|airpods|headphones)('s)?( is| are| was)?"
            r"( literally| probably| about)? (going to|gonna|about to) die\b"
        ),
    ],
    "not-alive": [r"\bwant to live (in|with|near|at|there|here|like|on)\b"],
    "harm-other": [
        r"\bshoot(ing)? my shot\b",
        # "I'll shoot him a text", "shoot my boss an email"
        (
            r"\bshoot(ing)? (him|her|them|someone|somebody|my \w+) (a |an )?(quick )?"
            r"(text|message|email|e-mail|dm|note|line|msg)\b"
        ),
        # "the kids are killing my vibe"
        r"\bkill(ing)? my (vibe|mood|buzz|battery|time|appetite|motivation|joy|plants?)\b",
    ],
    "method": [
        r"\bshoot(ing)? my ?self in the foot\b",  # "I'll shoot myself in the foot if I say yes"
        (
            r"\btook all my (pills|meds|medication) (on time|as prescribed|like (i was supposed to|"
            r"(my|the) doctor said))\b"
        ),
    ],
    "hurt-other": [
        # "I'm going to hurt my back lifting that"
        (
            r"\b(hurt|harm) my (back|knee|knees|neck|shoulder|ankle|wrist|leg|arm|foot|feet|hand|head|"
            r"eyes|chances|grades?|career|reputation|credit)\b"
        ),
    ],
    "self-harm": [
        r"\bhurt myself (at the gym|playing \w+|running|lifting|skiing|cooking|moving)\b"
    ],
}

# Medication (M3-09). Plain Qwen is served with no adapter for MS3, and the prompt
# rule alone ("never talk about medication or doses") is not a guarantee. These
# rules catch the patient asking for a medication decision, not every mention:
# "my sertraline makes me tired" still gets a normal reply.
MEDICATION_RULES: list[tuple[str, str]] = [
    # "should I stop my meds", "can I double my dose", "thinking of coming off sertraline"
    # past tense too: "I stopped taking my meds", "I skipped my meds", "I doubled my dose"
    (
        "med-change",
        (
            r"\b(stop|stopped|stopping|quit|quitting|skip|skipped|skipping|double|doubled|"
            r"doubling|increase|increased|increasing|decrease|decreased|decreasing|lower|"
            r"lowered|lowering|raise|raised|raising|halve|halved|cut down|cut back|come off|"
            r"came off|coming off|go off|went off|going off|get off|got off|wean off|taper|"
            r"tapered|tapering)( taking| on)?( my| the| your)? (\w+ )?" + _MEDS + r"\b"
            # any drug name after "taking my": "I stopped taking my lisinopril"
            r"|\b(stop|stopped|stopping|quit|quitting|skip|skipped|skipping) taking my "
            r"(?!(car|bike|bus|train|dog|dogs|kids?|son|daughter|lunch|time|classes|class|notes|"
            r"walks?|advice|calls?|shifts?|turn)\b)\w+"
            # "I'm going to take more pills tonight"
            r"|\b(take|taking|took) (more|extra|another|some more|a few more|a couple more)"
            r"( of)?( my| the)? (\w+ )?" + _MEDS + r"\b"
        ),
    ),
    # "how many mg should I take", "what dose of xanax is safe"
    (
        "med-dose",
        (
            r"\b(how (many|much)|what|which|what's|whats|right|safe|max|maximum) "
            r"(\w+ ){0,3}(mg|milligrams?|dose|dosage|pills|tablets)\b"
            r"|\b\d+ ?(mg|milligrams?)\b"
        ),
    ),
    # "can I drink on my antidepressants", "is it ok to mix xanax and alcohol"
    (
        "med-mix",
        (
            r"\b(drink|drinking|alcohol|wine|beer|weed|cannabis|mix|mixing|combine|combining)\b"
            r"(\s\S+){0,6}\s" + _MEDS + r"\b"
            r"|\b" + _MEDS + r"(\s\S+){0,6}\s(alcohol|wine|beer|weed|cannabis|drinking)\b"
        ),
    ),
    # "should I take my meds today", "is it safe to take two pills", "do I need more medication"
    (
        "med-should",
        (
            r"\b(should i|can i|could i|do i need|is it (ok|okay|safe|bad|fine)|"
            r"would it be (ok|okay|safe|bad)|am i allowed)\b(\s\S+){0,6}\s" + _MEDS + r"\b"
        ),
    ),
]

MEDICATION_RULES.append(
    # "what medication should I take", "which antidepressant is best", "do you think I need
    # medication", "can you prescribe me something", "what can I take to sleep"
    (
        "med-advice",
        (
            r"\b(what|which)( \w+){0,2} "
            + _MEDS
            + r"( \w+){0,3} (should|best|better|works?|would)\b"
            r"|\b(do you think|you think|do u think) i (need|should (take|try|be on|start))( \w+){0,2} "
            + _MEDS
            + r"\b"
            r"|\b(can|could|will|would) you prescribe\b"
            r"|\bwhat (can|should|could) i take (to (help me )?(sleep|calm down|relax|fall asleep|stay awake|feel better)"
            r"|for (my |the |a )?(sleep|pain|anxiety|stress|depression|headaches?|migraines?|insomnia|"
            r"panic( attacks)?|nerves|mood))\b"
        ),
    ),
)

MEDICATION_EXCEPTIONS: dict[str, list[str]] = {
    # "I remembered to take my meds", "my reminder to take my pills": routine, not a question
    "med-should": [
        r"\b(remember(ed)?|reminder|forgot|forget) to take (my|the) " + _MEDS + r"\b",
        # "can I tell you how my medication makes me feel", "can I talk about my meds"
        r"\bcan i (tell you|talk|talk to you|vent|share|ask you something)( about)?\b",
    ],
    # "my doctor said I should stop my meds and I'm scared": the prescriber's decision, not a question
    "med-change": [
        (
            r"\b(doctor|psychiatrist|prescriber|gp|nurse|pharmacist|nurse practitioner) "
            r"(said|says|told me|wants me|asked me)( that)?( i should| to| i need to| i have to| i can)?"
            r"( \w+){0,4} " + _MEDS + r"\b"
        )
    ],
    "med-dose": [r"\bwhat a (\w+ )?dose\b"],  # "what a dose of reality"
}

MEDICATION_REPLY = (
    "I can't give advice about medication or doses, and this is too important to "
    "guess about. The person who prescribed it, or a pharmacist, is the right person "
    "to ask; please contact them before changing anything. If you feel unwell right "
    "now, call 911. I'm still here if you'd like to talk about how you're feeling."
)

CAMERA_RULES: list[tuple[str, str]] = [
    (
        "camera-question",
        (
            r"\b(can|do|could) you (see|watch|look at) (me|my (face|camera|video))"
            r"( right now| now| at all| through (the|my|this) (camera|webcam|screen))?$"
            r"|\bare you (recording|watching|filming) me\b"
            r"|\bare you (recording|filming|storing|saving|keeping) (my |the |this )?(video|videos|camera|face|images?|pictures?|photos?|footage)\b"
            r"|\b(do|will) you (keep|store|save|record|share)( \w+)? (video|videos|camera|face|images?|recording)\b"
            r"|\bis (the|my|this) camera (recording|saving|storing|on|off|watching)\b"
            r"|\bwhat (does|do|did|can) (the|my|this|your) (camera|software|app) (think|see|say|show|know)\b"
            r"|\b(can|could|does|do|will) (the|my|this|your) (camera|software|app)\b.{0,40}\b(guess|read|tell|know)\b.{0,20}\b(feel|feeling|feelings|emotion|emotions|mood)\b"
            r"|\bcan you (guess|read|tell)\b.{0,20}\b(feeling|feelings|emotion|emotions|mood)\b.{0,30}\bcamera\b"
        ),
    ),
]
CAMERA_REPLY = (
    "I only read your messages, so I can't see you. If your camera is on, software makes a rough "
    "estimate of your expression, and you can see it in the panel on this screen. No video or images "
    "are recorded or stored, though a summary of the estimates can be shared with your clinician. "
    "You can turn the camera off at any time."
)

_COMPILED_CAMERA = [(rid, re.compile(p)) for rid, p in CAMERA_RULES]
_COMPILED_CRISIS = [(rid, re.compile(p)) for rid, p in CRISIS_RULES]
_COMPILED_MEDICATION = [(rid, re.compile(p)) for rid, p in MEDICATION_RULES]
_COMPILED_EXCEPTIONS = {
    rid: [re.compile(p) for p in patterns]
    for rid, patterns in {**CRISIS_EXCEPTIONS, **MEDICATION_EXCEPTIONS}.items()
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


def _first_rule(rules: list[tuple[str, re.Pattern]], text: str) -> str | None:
    for rule_id, pattern in rules:
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
    """Message in, crisis / medication / camera / no hit out, checked in that order."""
    text = normalise(message)
    if rule_id := _first_rule(_COMPILED_CRISIS, text):
        return SafetyResult("crisis", rule_id)
    if rule_id := _first_rule(_COMPILED_MEDICATION, text):
        return SafetyResult("medication", rule_id)
    if rule_id := _first_rule(_COMPILED_CAMERA, text):
        return SafetyResult("camera", rule_id)
    return SafetyResult(None)


def crisis_payload(review_flag_created: bool) -> dict:
    """CrisisPayload from docs/contracts/api-gateway.openapi.yaml."""
    return {
        "message": CRISIS_MESSAGE,
        "resources": CRISIS_RESOURCES,
        "review_flag_created": review_flag_created,
    }
