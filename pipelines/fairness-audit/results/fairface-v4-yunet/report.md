# M3-02 fairness audit

**Largest gap: the gate passing when a face is found, by age: 10-19 69.9% vs more than 70 40.0%, a gap of 29.9 points, the two groups' 95% intervals do not overlap.**

Model `cv-vit-b16-v4`, candidate (not yet served); data FairFace validation (padding 0.25) (`fairface/v1-val`). 9399 of 10954 photos in scope; ages 0-2, 3-9 reported separately. Gaps name only groups with at least 100 photos.

FairFace has no expression labels: these numbers show how differently the model behaves per group, not how accurate it is. Non-overlapping 95% intervals are a screen for gaps worth a closer look, not a formal significance test.

## Key gaps

| Attribute | Measure | Highest | Lowest | Gap (points) | Intervals separate |
|---|---|---|---|---|---|
| race | a trusted camera reading (face found and gate passed) | Southeast Asian 64.1% | Middle Eastern 49.0% | 15.1 | yes |
| race | being read as happy | Black 50.7% | Middle Eastern 40.0% | 10.8 | yes |
| race | being read as negative (angry, disgust, fear or sad) | Middle Eastern 17.0% | Southeast Asian 11.1% | 5.9 | yes |
| race | the face detector finding a face | Southeast Asian 93.8% | Black 88.6% | 5.2 | yes |
| race | mean confidence (top probability) | Southeast Asian 49.5% | Middle Eastern 46.1% | 3.4 | yes |
| gender | being read as happy | Female 57.7% | Male 38.9% | 18.8 | yes |
| gender | a trusted camera reading (face found and gate passed) | Female 63.1% | Male 52.4% | 10.8 | yes |
| gender | mean confidence (top probability) | Female 49.8% | Male 46.6% | 3.3 | yes |
| gender | the face detector finding a face | Female 92.5% | Male 89.4% | 3.0 | yes |
| gender | being read as negative (angry, disgust, fear or sad) | Male 13.8% | Female 12.7% | 1.1 | no |
| age | a trusted camera reading (face found and gate passed) | 10-19 64.4% | more than 70 35.6% | 28.8 | yes |
| age | being read as negative (angry, disgust, fear or sad) | more than 70 26.3% | 20-29 10.9% | 15.3 | yes |
| age | being read as happy | 30-39 50.9% | more than 70 38.1% | 12.8 | yes |
| age | mean confidence (top probability) | 20-29 49.6% | more than 70 43.0% | 6.6 | yes |
| age | the face detector finding a face | 10-19 92.1% | 60-69 86.3% | 5.8 | yes |

## By race

| Group | Photos | face_found | gate_ok | share_negative | share_happy | confidence |
|---|---|---|---|---|---|---|
| Black | 1275 | 88.6% | 55.1% | 11.3% | 50.7% | 47.5% |
| East Asian | 1281 | 90.4% | 60.6% | 11.6% | 49.5% | 48.8% |
| Indian | 1315 | 91.9% | 55.8% | 14.1% | 43.8% | 47.2% |
| Latino_Hispanic | 1426 | 92.8% | 58.3% | 14.4% | 49.5% | 48.7% |
| Middle Eastern | 1083 | 89.4% | 49.0% | 17.0% | 40.0% | 46.1% |
| Southeast Asian | 1174 | 93.8% | 64.1% | 11.1% | 48.6% | 49.5% |
| White | 1845 | 89.6% | 58.3% | 13.5% | 50.5% | 48.6% |

Top emotion per group:

| Group | Photos | share_angry | share_disgust | share_fear | share_happy | share_neutral | share_sad | share_surprise |
|---|---|---|---|---|---|---|---|---|
| Black | 1275 | 2.5% | 2.2% | 0.3% | 50.7% | 37.2% | 6.3% | 0.8% |
| East Asian | 1281 | 1.5% | 1.6% | 0.4% | 49.5% | 37.9% | 8.1% | 1.0% |
| Indian | 1315 | 3.0% | 2.0% | 0.5% | 43.8% | 41.3% | 8.7% | 0.8% |
| Latino_Hispanic | 1426 | 3.1% | 2.7% | 0.2% | 49.5% | 35.6% | 8.4% | 0.5% |
| Middle Eastern | 1083 | 3.0% | 3.6% | 0.5% | 40.0% | 41.2% | 9.9% | 1.8% |
| Southeast Asian | 1174 | 0.9% | 1.5% | 0.0% | 48.6% | 39.8% | 8.6% | 0.6% |
| White | 1845 | 3.0% | 1.8% | 0.2% | 50.5% | 33.9% | 8.4% | 2.1% |

## By gender

| Group | Photos | face_found | gate_ok | share_negative | share_happy | confidence |
|---|---|---|---|---|---|---|
| Female | 4471 | 92.5% | 63.1% | 12.7% | 57.7% | 49.8% |
| Male | 4928 | 89.4% | 52.4% | 13.8% | 38.9% | 46.6% |

Top emotion per group:

| Group | Photos | share_angry | share_disgust | share_fear | share_happy | share_neutral | share_sad | share_surprise |
|---|---|---|---|---|---|---|---|---|
| Female | 4471 | 1.6% | 1.5% | 0.3% | 57.7% | 28.8% | 9.3% | 0.8% |
| Male | 4928 | 3.3% | 2.8% | 0.3% | 38.9% | 45.9% | 7.4% | 1.4% |

## By age

| Group | Photos | face_found | gate_ok | share_negative | share_happy | confidence |
|---|---|---|---|---|---|---|
| 10-19 | 1181 | 92.1% | 64.4% | 11.0% | 44.4% | 49.6% |
| 20-29 | 3300 | 92.0% | 63.2% | 10.9% | 50.3% | 49.6% |
| 30-39 | 2330 | 90.3% | 58.5% | 12.2% | 50.9% | 48.5% |
| 40-49 | 1353 | 90.1% | 48.4% | 15.8% | 44.2% | 45.9% |
| 50-59 | 796 | 89.4% | 45.7% | 19.3% | 43.8% | 45.1% |
| 60-69 | 321 | 86.3% | 41.1% | 22.4% | 41.7% | 43.5% |
| more than 70 | 118 | 89.0% | 35.6% | 26.3% | 38.1% | 43.0% |

Top emotion per group:

| Group | Photos | share_angry | share_disgust | share_fear | share_happy | share_neutral | share_sad | share_surprise |
|---|---|---|---|---|---|---|---|---|
| 10-19 | 1181 | 1.3% | 1.4% | 0.2% | 44.4% | 43.9% | 8.2% | 0.7% |
| 20-29 | 3300 | 2.1% | 1.2% | 0.3% | 50.3% | 37.6% | 7.3% | 1.2% |
| 30-39 | 2330 | 2.6% | 1.7% | 0.4% | 50.9% | 35.3% | 7.5% | 1.5% |
| 40-49 | 1353 | 2.3% | 3.3% | 0.3% | 44.2% | 38.9% | 9.9% | 1.1% |
| 50-59 | 796 | 4.3% | 4.5% | 0.0% | 43.8% | 36.1% | 10.6% | 0.8% |
| 60-69 | 321 | 6.9% | 5.6% | 0.0% | 41.7% | 35.2% | 10.0% | 0.6% |
| more than 70 | 118 | 2.5% | 6.8% | 1.7% | 38.1% | 34.7% | 15.3% | 0.8% |

## Children (out of scope, for reference)

| Group | Photos | face_found | gate_ok | share_negative | share_happy | confidence |
|---|---|---|---|---|---|---|
| 0-2 | 199 | 97.5% | 56.3% | 14.1% | 24.6% | 46.3% |
| 3-9 | 1356 | 94.3% | 60.8% | 12.2% | 36.4% | 48.0% |

## Provenance

- checkpoint sha256: `5b003e0a18578e570672d2b58742548b91247a75b9ba3bd5f484750eee1e862b`
- labels sha256: `3d8e4e47183d48c1014986308c752dfe6e242f2e7e1509a6d4d1481b67013a5c`
- predictions sha256: `ab20b0c7a3eebb6c69e798d87d6332da10adce214739525817254bb8c1b2ccc0`
- FairFace: `HuggingFaceM4/FairFace` at `54d573cdb8b5af490ba8da9da2799628f6e5c496`
- code: `a36cf189200c3fbaad26ac5e2293109e733617d6`
- gate (gateway defaults): top >= 0.45, margin >= 0.05, stability >= 0.5, window 10.0 s, at least 3 frames, face in >= 0.5 of frames; a photo is one steady frame
