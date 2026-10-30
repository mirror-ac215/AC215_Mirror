# M3-02 fairness audit

**Largest gap: the gate passing when a face is found, by age: 20-29 71.7% vs more than 70 30.6%, a gap of 41.1 points, larger than the noise in either group (95% intervals do not overlap).**

Model `cv-vit-b16-v4`, data FairFace validation (padding 0.25) (`fairface/v1-val`). 9399 of 10954 photos in scope; ages 0-2, 3-9 reported separately. Gaps name only groups with at least 100 photos.

FairFace has no expression labels: these numbers show how differently the model behaves per group, not how accurate it is.

## Key gaps

| Attribute | Measure | Highest | Lowest | Gap (points) | Beyond noise |
|---|---|---|---|---|---|
| race | the face detector finding a face | Southeast Asian 55.0% | Black 33.8% | 21.2 | yes |
| race | a trusted camera reading (face found and gate passed) | Southeast Asian 38.4% | Black 20.5% | 17.9 | yes |
| race | being read as happy | Latino_Hispanic 49.1% | Middle Eastern 38.7% | 10.4 | yes |
| race | being read as negative (angry, disgust, fear or sad) | Middle Eastern 18.5% | East Asian 12.3% | 6.2 | yes |
| race | mean confidence (top probability) | Southeast Asian 48.7% | Middle Eastern 45.8% | 2.9 | yes |
| gender | being read as happy | Female 56.2% | Male 38.3% | 17.9 | yes |
| gender | a trusted camera reading (face found and gate passed) | Female 38.3% | Male 25.2% | 13.2 | yes |
| gender | the face detector finding a face | Female 54.6% | Male 42.2% | 12.4 | yes |
| gender | mean confidence (top probability) | Female 49.3% | Male 46.1% | 3.3 | yes |
| gender | being read as negative (angry, disgust, fear or sad) | Male 15.3% | Female 13.4% | 1.9 | no |
| age | a trusted camera reading (face found and gate passed) | 20-29 35.6% | more than 70 12.7% | 22.9 | yes |
| age | being read as negative (angry, disgust, fear or sad) | more than 70 28.8% | 10-19 11.4% | 17.4 | yes |
| age | being read as happy | 20-29 49.9% | more than 70 34.7% | 15.2 | yes |
| age | the face detector finding a face | 10-19 50.4% | 60-69 38.9% | 11.4 | yes |
| age | mean confidence (top probability) | 20-29 49.2% | more than 70 41.6% | 7.6 | yes |

## By race

| Group | Photos | face_found | gate_ok | share_negative | share_happy | confidence |
|---|---|---|---|---|---|---|
| Black | 1275 | 33.8% | 20.5% | 12.8% | 48.9% | 46.9% |
| East Asian | 1281 | 54.0% | 36.3% | 12.3% | 47.9% | 48.2% |
| Indian | 1315 | 51.2% | 32.1% | 14.8% | 43.7% | 47.0% |
| Latino_Hispanic | 1426 | 52.8% | 36.0% | 15.6% | 49.1% | 48.4% |
| Middle Eastern | 1083 | 44.6% | 25.9% | 18.5% | 38.7% | 45.8% |
| Southeast Asian | 1174 | 55.0% | 38.4% | 12.4% | 48.1% | 48.7% |
| White | 1845 | 45.6% | 30.3% | 14.6% | 49.0% | 47.9% |

Top emotion per group:

| Group | Photos | share_angry | share_disgust | share_fear | share_happy | share_neutral | share_sad | share_surprise |
|---|---|---|---|---|---|---|---|---|
| Black | 1275 | 2.8% | 1.6% | 0.3% | 48.9% | 37.3% | 8.0% | 1.1% |
| East Asian | 1281 | 1.7% | 1.4% | 0.5% | 47.9% | 38.0% | 8.7% | 1.8% |
| Indian | 1315 | 3.2% | 2.1% | 0.2% | 43.7% | 40.5% | 9.2% | 1.1% |
| Latino_Hispanic | 1426 | 3.0% | 3.6% | 0.3% | 49.1% | 34.8% | 8.8% | 0.5% |
| Middle Eastern | 1083 | 3.6% | 3.3% | 0.6% | 38.7% | 40.5% | 10.9% | 2.3% |
| Southeast Asian | 1174 | 1.4% | 1.7% | 0.3% | 48.1% | 38.5% | 9.0% | 1.0% |
| White | 1845 | 2.7% | 2.4% | 0.2% | 49.0% | 34.0% | 9.4% | 2.3% |

## By gender

| Group | Photos | face_found | gate_ok | share_negative | share_happy | confidence |
|---|---|---|---|---|---|---|
| Female | 4471 | 54.6% | 38.3% | 13.4% | 56.2% | 49.3% |
| Male | 4928 | 42.2% | 25.2% | 15.3% | 38.3% | 46.1% |

Top emotion per group:

| Group | Photos | share_angry | share_disgust | share_fear | share_happy | share_neutral | share_sad | share_surprise |
|---|---|---|---|---|---|---|---|---|
| Female | 4471 | 1.7% | 1.5% | 0.3% | 56.2% | 29.3% | 9.9% | 1.1% |
| Male | 4928 | 3.5% | 3.1% | 0.4% | 38.3% | 44.7% | 8.4% | 1.8% |

## By age

| Group | Photos | face_found | gate_ok | share_negative | share_happy | confidence |
|---|---|---|---|---|---|---|
| 10-19 | 1181 | 50.4% | 35.2% | 11.4% | 43.7% | 48.7% |
| 20-29 | 3300 | 49.7% | 35.6% | 12.1% | 49.9% | 49.2% |
| 30-39 | 2330 | 49.9% | 33.7% | 13.2% | 49.2% | 48.0% |
| 40-49 | 1353 | 44.5% | 25.1% | 15.7% | 43.9% | 45.5% |
| 50-59 | 796 | 43.7% | 21.4% | 22.9% | 42.0% | 45.0% |
| 60-69 | 321 | 38.9% | 16.5% | 25.5% | 37.7% | 42.6% |
| more than 70 | 118 | 41.5% | 12.7% | 28.8% | 34.7% | 41.6% |

Top emotion per group:

| Group | Photos | share_angry | share_disgust | share_fear | share_happy | share_neutral | share_sad | share_surprise |
|---|---|---|---|---|---|---|---|---|
| 10-19 | 1181 | 1.3% | 1.3% | 0.2% | 43.7% | 43.9% | 8.7% | 1.0% |
| 20-29 | 3300 | 2.1% | 1.2% | 0.3% | 49.9% | 36.4% | 8.4% | 1.6% |
| 30-39 | 2330 | 2.8% | 1.9% | 0.4% | 49.2% | 35.8% | 8.1% | 1.8% |
| 40-49 | 1353 | 2.6% | 3.0% | 0.2% | 43.9% | 39.0% | 9.8% | 1.4% |
| 50-59 | 796 | 4.5% | 5.8% | 0.1% | 42.0% | 34.2% | 12.4% | 1.0% |
| 60-69 | 321 | 7.5% | 6.9% | 0.6% | 37.7% | 35.8% | 10.6% | 0.9% |
| more than 70 | 118 | 1.7% | 8.5% | 1.7% | 34.7% | 36.4% | 16.9% | 0.0% |

## Children (out of scope, for reference)

| Group | Photos | face_found | gate_ok | share_negative | share_happy | confidence |
|---|---|---|---|---|---|---|
| 0-2 | 199 | 32.7% | 16.1% | 18.1% | 23.1% | 45.3% |
| 3-9 | 1356 | 49.9% | 31.6% | 13.8% | 36.2% | 47.1% |

## Provenance

- checkpoint sha256: `5b003e0a18578e570672d2b58742548b91247a75b9ba3bd5f484750eee1e862b`
- labels sha256: `3d8e4e47183d48c1014986308c752dfe6e242f2e7e1509a6d4d1481b67013a5c`
- predictions sha256: `3adb75dd0390d74ea7fbd43ebfe94726410c7f061b5ca08879bbfd0a2c292477`
- code: `5c77271a0706b0a045661f6e6971ba3ce3c7b8ee`
- gate: top >= 0.45, margin >= 0.05
