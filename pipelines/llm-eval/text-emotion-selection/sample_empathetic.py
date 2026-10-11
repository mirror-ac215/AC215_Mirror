"""Sample 50 messages from EmpatheticDialogues for M2-11 (seed 215).

Source: EmpatheticDialogues (Rashkin et al., ACL 2019), Facebook AI Research.
Download: https://dl.fbaipublicfiles.com/parlai/empatheticdialogues/empatheticdialogues.tar.gz
Uses each conversation's prompt (a first-person situation), one per
conversation, from the test split. ED's 32 emotions are grouped only to
balance the sample; Julie labels every message herself.
Usage: python3 sample_empathetic.py empatheticdialogues/test.csv
"""
import csv
import random
import re
import sys

GROUPS = {
    "anger": ["angry", "annoyed", "furious", "jealous"],
    "disgust": ["disgusted"],
    "fear": ["afraid", "anxious", "apprehensive", "terrified"],
    "joy": ["joyful", "excited", "content", "grateful", "hopeful",
            "proud", "confident", "caring", "trusting", "faithful",
            "prepared", "anticipating"],
    "sadness": ["sad", "devastated", "lonely", "disappointed",
                "guilty", "ashamed", "embarrassed", "nostalgic",
                "sentimental"],
    "surprise": ["surprised", "impressed"],
}
QUOTA = {"sadness": 10, "fear": 9, "anger": 8,
         "joy": 8, "surprise": 8, "disgust": 7}

SELF_HARM = re.compile(
    r"suicid"
    r"|kill myself"
    r"|self.?harm"
    r"|end my life"
    r"|cutting",
    re.I,
)
DATED = re.compile(
    r"covid"
    r"|corona"
    r"|pandemic"
    r"|lockdown"
    r"|quarantin"
    r"|vaccin"
    r"|election",
    re.I,
)
ed_to_group = {e: g for g, es in GROUPS.items() for e in es}

convs = {}
with open(sys.argv[1], encoding="utf-8") as f:
    next(f)
    for line in f:
        parts = line.rstrip("\n").split(",")
        if len(parts) < 4:
            continue
        conv_id, emotion, prompt = parts[0], parts[2], parts[3]
        if conv_id not in convs:
            text = " ".join(prompt.replace("_comma_", ",").split())
            convs[conv_id] = (emotion, text)

rng = random.Random(215)
rows, seen = [], set()
for group, n in QUOTA.items():
    pool = []
    for cid, (emo, txt) in sorted(convs.items()):
        if ed_to_group.get(emo) != group:
            continue
        if not 30 <= len(txt) <= 300:
            continue
        if SELF_HARM.search(txt) or DATED.search(txt):
            continue
        pool.append((cid, emo, txt))
    rng.shuffle(pool)
    picked = 0
    for cid, emo, txt in pool:
        if txt.lower() in seen:
            continue
        seen.add(txt.lower())
        rows.append((cid, emo, txt))
        picked += 1
        if picked == n:
            break
rng.shuffle(rows)

with open("m2-11_messages_to_label.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["id", "text", "label", "second_label", "notes"])
    for k, (cid, emo, txt) in enumerate(rows, 1):
        w.writerow([f"m{k:02d}", txt, "", "", ""])

with open("m2-11_source_key.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["id", "ed_conv_id", "ed_emotion"])
    for k, (cid, emo, txt) in enumerate(rows, 1):
        w.writerow([f"m{k:02d}", cid, emo])

print(len(rows), "messages written to m2-11_messages_to_label.csv")
