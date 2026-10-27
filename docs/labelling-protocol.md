# Labelling protocol for Mirror's own webcam dataset (M3-22)

**Status:** draft for team review (Oct 2026). **Used by:** M3-20 (self-report check-in) and the M4-09 evaluation.
**Owner:** Mostafa. **Reviewer:** Julie.

## Why

Every number we have for the camera model comes from public datasets (FER-2013, FER+, Aff-Wild2).
None of them looks exactly like Mirror: a laptop webcam, home lighting, someone chatting. This
protocol collects a small dataset that does, so we can answer one question honestly:

> When the gate says the face reading is "ok", how often does it match what the person says they feel?

It is a **validation set** first (the MS1 feedback asked for one); it is too small to train on.

## Who takes part

- The three team members and a few **adult volunteers** (friends or classmates). No minors, no
  patients, no one currently in distress.
- **Before any volunteer outside the team is recorded,** we confirm with our TF (Patrick), and with
  Harvard's IRB if he advises it (a quick "not human-subjects research" determination, since face
  images are biometric data), that this is acceptable for a course project. Team-only sessions can
  start before that.
- **No pressure:** volunteers are invited by Owen or Julie, never by the session lead, and saying no
  is fine and is never brought up again.
- Everyone signs the consent below. Taking part is voluntary and anyone can stop at any time,
  without giving a reason.

## Consent (shown in the app before the session; two separate choices)

> **Mirror research session.** This is a student project (Harvard AC215), not a clinical service.
> For about 20 minutes you will chat with Mirror and, every few minutes, tell us how you feel.
>
> **1. Check-ins (required to take part).** We store your check-in answers, the camera model's
> estimates during the session (numbers only, about one per second, no images), the text model's
> reading of your last message before each check-in (numbers only, never your words) and the time.
> They are stored under a random ID, not your name.
>
> **2. Camera frames (optional).** If you also tick this box, we keep one still image per second of
> your face during the session, including a short block at the end where we ask you to show each
> emotion on purpose. Images are stored only in our private project storage, are seen only by the
> three team members, and are never published; course staff see summary numbers only.
>
> You can stop at any time and ask us to delete everything we stored about you, at any time.
> All data is deleted at the end of the course (December 2026) unless you agree otherwise.

If the frames box is not ticked, the camera still runs (the model needs it) but no image is ever
written to disk.

## What people report (check-in)

A small panel over the chat:

- **How do you feel right now?** one of Mirror's 7 emotions: angry, disgusted, afraid, happy,
  neutral, sad, surprised, or **"none of these"**.
- **How strongly?** 1 (a little), 2 (clearly), 3 (strongly). Not asked for neutral or "none of these".
- **Skip** is always allowed.

**When:** every **3 minutes**, and once right after each task of the session script. The model's
reading is captured at the moment the panel opens (before the person answers, so answering does not
change the face we score).

## Session script (about 21 minutes)

| Part | Minutes | What happens | Why |
|---|---|---|---|
| 1. Settle in | 3 | Neutral chat with Mirror (plans for the week, the weather) | Baseline neutral faces |
| 2. Happy recall | 3 | "Tell Mirror about a recent moment that made you laugh or feel proud" | Spontaneous happiness |
| 3. Sad recall | 3 | "Tell Mirror about a small disappointment, something mild" | Spontaneous sadness, kept mild |
| 4. Annoyed recall | 3 | "Tell Mirror about something that annoyed you recently" | Spontaneous anger/irritation |
| 5. Surprise | 2 | A short surprising fact or video clip, chosen by the session lead | Spontaneous surprise |
| 6. Cool down | 2 | Neutral chat again | Ends on a calm note |
| 7. Posed block | 2 | "Please *show* each emotion for 5 seconds" (all 7) | **Kept separate and labelled `posed`**: useful for comparison, never mixed with spontaneous data |
| 8. Debrief | 1 | The session lead (not Mirror) asks how they feel now, reminds them of 988 and who to contact, and confirms they are OK; optionally ends on something light of their choice | Ends with a person, not a screen |

**Wellbeing:** the recall prompts ask for *mild* memories, and fear and disgust are not elicited on
purpose (if they occur, they are labelled like any other emotion). Crisis resources (988) are shown
to everyone at the start, and Mirror's normal safety check stays on.

**Stop rule:** the session lead stops the session when (a) a check-in reports **sad or afraid at
intensity 3**, (b) Mirror's **crisis check fires**, (c) the lead judges that the person is
distressed, or (d) the person asks; no reason needed. Any stop goes straight to the debrief.

**If the crisis check fires:** Mirror withholds its reply and shows 988. The session lead steps in
at once, the session ends there, and the debrief follows. The data is kept only if the person agrees
afterwards.

## What is stored

Per session, under a random participant ID (the ID-to-name list is kept by the session lead only,
outside the bucket, and deleted with the data):

| Item | Always | Only with frames consent |
|---|---|---|
| Check-ins: time, emotion, intensity, part of the script, `posed` flag | yes | |
| Gate output at each check-in: status and top-2 (the context object's `visual` block) | yes | |
| Text module's top-2 for the last message before each check-in (numbers only, no text); "no reading" if no message was sent in the 60 s before it | yes | |
| Per-second model probabilities (numbers only) | yes | |
| One face image per second (JPEG) | | yes |
| Session metadata: date, camera on/off, consent choices, model version | yes | |

No chat text is stored for this dataset.

## Labelling the frames (two raters)

For sessions with frames consent, Julie and Mostafa each label, independently, the frame at every
check-in moment and the posed block (not every second). Neither sees the self-report or the other's
label while labelling. We report how often the two agree (and Cohen's kappa) and how often each
agrees with the self-report. One labeller makes mistakes (M3-18: FER-2013's single labels disagree
with the 10-annotator FER+ majority on about a third of photos); two let us measure that.
Disagreements are reported, not overwritten.

## Storage and versioning

- Location: the private bucket `gs://mirror-ac215-data/data/raw/selfreport/v1/`, versioned with DVC
  like our other data. Never in Git, never in W&B (W&B gets aggregate numbers only).
- Access: the three team members.
- **Split by person:** a person's sessions are all in one split. When the set is used for testing,
  no one in it may also be in any training data.

## Deletion

- On request, at any time: the session lead deletes that ID's files from the bucket and from DVC
  storage and confirms by message. Any aggregate number already reported is recomputed without them.
- At the end of the course (December 2026): everything is deleted unless the person agreed in writing
  to a longer period.

## What we report (M4-09)

For every check-in that was not skipped:

1. **Agreement:** when the gate said "ok", how often its top emotion matches the self-report (overall
   and per emotion), and how often the gate said "ok" at all.
2. **The same for the posed block**, reported separately.
3. **Face vs text:** the same agreement for the text-emotion module (from the stored top-2 at each
   check-in), to show which signal tracks self-reports better (MS1 feedback: rely on the non-text
   signal only where it earns it).
4. **Labeller agreement:** the two raters with each other and with the self-reports (see above).

These are the real-world counterparts of the Aff-Wild2 sweep in `services/api-gateway/README.md`
(gate "ok" 31 % of the time, right 64 %).

## Roles

| Role | Who |
|---|---|
| Session lead (runs the session, holds the ID list, handles deletion) | Mostafa |
| Check-in UI and storage (M3-20) | Mostafa, review Owen |
| Webcam capture the check-in builds on (M3-11) | Owen |
| Analysis (M4-09) | Julie and Mostafa |
| Inviting volunteers (never the session lead) | Owen or Julie |
| Frame labelling (two raters) | Julie and Mostafa |
| First team-only test session (check-in panel + script) | the three team members |
