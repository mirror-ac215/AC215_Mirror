// Plain-language messages for failed calls on the patient screens (M4-24).
// The API client throws errors whose message ends in "failed with <status>"
// (`ApiError` keeps the same message), and a network failure throws a TypeError
// with no status.

/** The HTTP status in a failed API call, or null when the request never got an answer. */
export function statusOf(error: unknown): number | null {
  if (!(error instanceof Error)) return null;
  const match = /failed with (\d{3})\b/.exec(error.message);
  return match ? Number(match[1]) : null;
}

export const LOGIN_WRONG = "Wrong email or password.";
export const LOGIN_TOO_MANY = "Too many attempts. Wait 5 minutes, then try again.";
export const LOGIN_UNREACHABLE =
  "We can't reach Mirror right now. Check your connection and try again.";

/** What the sign-in screen says for a failed login. */
export function loginErrorMessage(error: unknown): string {
  const status = statusOf(error);
  if (status === 400 || status === 401 || status === 422) return LOGIN_WRONG;
  if (status === 429) return LOGIN_TOO_MANY;
  return LOGIN_UNREACHABLE;
}

export const MESSAGE_NOT_SENT = "Your message didn't send. Check your connection and try again.";

/** The gateway accepts 1 to 4000 characters per message (api-gateway.openapi.yaml). */
export const MAX_MESSAGE_LENGTH = 4000;
