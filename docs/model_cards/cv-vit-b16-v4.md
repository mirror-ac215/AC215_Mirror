# Model card: cv-vit-b16-v4

Mirror's facial-expression model. **Owner:** Mostafa (M4-10). **Last updated:** Nov 4, 2026.

**In one sentence:** it estimates which of 7 expressions a face is showing, and it is an estimate of an expression, not a measure of how someone feels.

## Model

| | |
|---|---|
| Version | `cv-vit-b16-v4` |
| Architecture | ViT-B/16 with a 7-class head |
| Classes | angry, disgust, fear, happy, neutral, sad, surprise |
| Input | One face crop: grayscale copied to 3 channels, resized to 224x224, ImageNet normalization |
| Output | 7 probabilities (softmax) |
| Face detection | Haar cascade in cv-service, before the model. No face means no reading |
| Served by | `cv-service`, on CPU (M3-03) |
| Artifact | `gs://mirror-ac215-data/models/cv/v4/vit_b16_v4.pth` (343,280,429 bytes) |
| SHA-256 | `5b003e0a18578e570672d2b58742548b91247a75b9ba3bd5f484750eee1e862b` |
| Training run | [W&B lgeo815r](https://wandb.ai/mog941-harvard-university/mirror/runs/lgeo815r), run C3 in `pipelines/cv-train/README.md` |

## Intended use

- One input to Mirror's chat companion, used only after the gateway has smoothed and gated readings over a 10-second window.
- Coursework and research only. It is not a medical device.

## Out of scope

- Diagnosing or assessing a person's mental state.
- Crisis detection. The crisis check reads text only, and the face is never an input to it (M3-07).
- Showing a reading to a clinician as a fact about a patient.
- Identifying people.
- Use without the patient's camera consent.
- Commercial use (see Limits).

## Training data

v4 is the inherited v3 model, fine-tuned on two sources, half of each epoch from each:

| Source | What it adds | Labels | Storage |
|---|---|---|---|
| Aff-Wild2 | Real video. Split by video, never by frame. Every 5th frame used, because neighbouring frames are near-duplicates | 8 labels mapped to our 7; "other" dropped | Licensed, frames stay local |
| FER+ | FER-2013 photos relabelled by 10 annotators each | Soft labels (vote shares). Ties and contempt, unknown or not-a-face photos dropped | MIT-licensed labels; images from FER-2013 |

v3 itself was trained on FER-2013 single-annotator labels.

## Training recipe

8 epochs (best: 7), seed 42, AdamW (learning rate 1e-5, weight decay 1e-4), cosine schedule, focal loss (gamma 2, label smoothing 0.1), weight averaging (EMA 0.999), batch size 32. The model was chosen on Aff-Wild2 validation (36 videos of our own split), never on test. Full command and all runs: `pipelines/cv-train/README.md`.

## Evaluation

Held-out test sets, each scored once with `cv-eval`.

| Test set | Size | v3 macro-F1 | **v4 macro-F1** | v4 accuracy |
|---|---|---|---|---|
| FER+ (10-annotator labels) | 6,722 photos | 0.609 | **0.720** | 0.805 |
| Aff-Wild2 (official validation videos, real video) | 10,772 frames, 45 videos | 0.260 | **0.337** | 0.436 |
| FER-2013 (single-annotator labels) | 7,178 photos | 0.645 | 0.588 | 0.632 |

**Release guard (D-005):** FER+ test macro-F1 >= 0.609, the v3 score. `mirror-cv-release-check` in `pipelines/cv-eval` enforces it: v4 passes with 0.7202.

**Why FER-2013 fell:** v4 learned what 10 people see, not what one labeller wrote, so it agrees less with FER-2013's labels. M3-18 showed those labels disagree with the crowd on about a third of the test photos.

### v4 F1 per class

| Class | FER+ | Aff-Wild2 | FER-2013 |
|---|---|---|---|
| happy | 0.92 | 0.61 | 0.87 |
| surprise | 0.85 | 0.33 | 0.76 |
| neutral | 0.80 | 0.46 | 0.58 |
| angry | 0.79 | 0.25 | 0.57 |
| sad | 0.65 | 0.30 | 0.49 |
| fear | 0.59 | 0.05 | 0.28 |
| disgust | 0.44 | 0.36 | 0.57 |

The Aff-Wild2 test set has only 3 fear videos and 9 sad videos, so those two scores are especially uncertain.

### How Mirror uses it: the gate

A single frame is noisy, so the gateway only trusts a steady reading. With the chosen thresholds (top probability 0.45, margin 0.05, stability 0.50), on 1,951 ten-second windows from the 36 Aff-Wild2 validation videos at 1 frame per second:

- The reading is trusted in **31%** of windows.
- When trusted, it is right **64%** of the time.
- It is trusted almost only for neutral, happy and surprise.

So fusion never lets a negative face reading lead (M3-06). These thresholds are provisional and have not been tested on our own users.

## Subgroup gaps (fairness audit, M3-02)

Audit of v4 on all 10,954 FairFace validation photos (9,399 in scope; children are reported separately). **FairFace has no expression labels, so this shows how differently the model behaves per group, not how accurate it is.** Accuracy gaps by group have not been measured.

**Largest gap: age.** When a face is found, the gate trusts the reading for 71.7% of people aged 20-29 but only 30.6% of people over 70 (41.1 points).

| Attribute | Measure | Highest | Lowest | Gap (points) |
|---|---|---|---|---|
| Age | Trusted reading | 20-29: 35.6% | Over 70: 12.7% | 22.9 |
| Age | Read as negative | Over 70: 28.8% | 10-19: 11.4% | 17.4 |
| Race | Face detector finds a face | Southeast Asian: 55.0% | Black: 33.8% | 21.2 |
| Race | Trusted reading | Southeast Asian: 38.4% | Black: 20.5% | 17.9 |
| Gender | Read as happy | Women: 56.2% | Men: 38.3% | 17.9 |
| Gender | Trusted reading | Women: 38.3% | Men: 25.2% | 13.2 |

What this means:

- **Older patients get the weakest signal,** with fewer trusted readings and more negative ones. A negative reading may reflect age, not mood.
- **The race gap comes mostly from the face detector.** Once a face is found, the gate passes for 58-70% of every race group. A modern detector is the most direct fix, and this audit can measure it.
- **The gender gap may be partly real,** because people may smile more in some photos. Without expression labels, the audit can't separate this from model bias.

Full tables: `pipelines/fairness-audit/results/fairface-v4/report.md`.

## Limits

- **Weak on real video.** 0.337 macro-F1 on Aff-Wild2. On video, fear is read as surprise and sadness as neutral in every run we tried. The limit is the data: Aff-Wild2 has only 16-28 training people per rare emotion.
- **Expression is not emotion.** People can smile through pain or look neutral while struggling.
- **Not tested on our own users.** No results yet from real webcam sessions (M3-20), so lighting, camera quality and patient populations are all unmeasured.
- **Training and serving differ.** cv-service's tight Haar crop differs from Aff-Wild2's aligned crops, and FER-2013's 48x48 photos.
- **Face detection is limited.** Haar found a face in only 48% of FairFace photos, which include profiles and tilted heads. It works mainly on frontal faces.
- **Near-duplicate photos.** FER-2013 has some near-duplicates across its parts, which lifts FER+ test scores a little for both v3 and v4. Aff-Wild2 test scores are not affected.
- **Not cleared for commercial use.** FER-2013's rights are unclear and Aff-Wild2 is licensed, so a commercial version would need different data.

## Privacy

Camera frames are never stored. cv-service scores a frame and discards it, and the gateway keeps only the probabilities, in a short window for each session.

## Performance

Target: p95 under 150 ms per frame on CPU (M3-03). No measurement has been recorded yet.

## Reproduce

```bash
uv run --project pipelines/cv-eval mirror-cv-release-check \
  --checkpoint /secure/path/vit_b16_v4.pth --output data/reports/release-check.json \
  --code-revision "$(git rev-parse HEAD)"
```

Build the data first with `mirror-prepare-ferplus`. Full details: `pipelines/cv-eval/README.md`.

## Next steps

- Re-measure on our own consented sessions (M3-20) and re-run the gate sweep.
- Try a modern face detector and re-run the fairness audit.
- Measure accuracy by group if RAF-DB access is granted.
