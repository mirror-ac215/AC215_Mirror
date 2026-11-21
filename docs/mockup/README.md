# Application mock-up (MS1 design → MS2 app skeleton)

These screens come from the MS1 clickable prototype (built in Lovable). The working MS2 app skeleton in `services/frontend` is built from them: sign-in, consent and the chat session already talk to the real API gateway (login with a token, camera consent, a streamed reply). Since then the crisis screen (MS3) and the clinician screens (MS4, M4-01) have been built too, so every screen below is in the app. For the current design, see [`docs/design.md`](../design.md).

| Screen | Status in the app |
|---|---|
| ![Sign in](01_sign_in.png) **Sign in**: patient or clinician | ✅ Real login against the gateway (token) |
| ![Consent](02_consent.png) **Consent**: camera off unless the user says yes | ✅ Consent passed to the session (`camera=true` only on opt-in) |
| ![Session](03_session_chat.png) **Session**: chat + expression panel | ✅ Reply streams from the gateway (SSE); expression panel shows an explicit "camera off" state without consent |
| ![Crisis](04_crisis_support.png) **Crisis support**: 988 + clinician notified | ✅ Built in MS3 (M3-07 crisis check, M3-12 chat UI) |
| ![Patients](05_clinician_patients.png) **Clinician: patient list** | ✅ Built in MS4 (M4-01, real data) |
| ![Patient detail](06_clinician_patient_detail.png) **Clinician: one patient's trend + review queue** | ✅ Built in MS4 (M4-01, real data) |
| ![User flow](07_user_flow.png) **User flow**: patient and clinician paths | Reference |

**Changed after MS1 feedback:** the clinician screens here show labels such as "anxious" and "low mood". In the real dashboard (M4-01) these are **expression estimates with a confidence level** ("tense-looking · low confidence · an estimate, not a feeling"). The face model cannot reliably measure how someone feels, so it must not present its output as a clinical fact.
