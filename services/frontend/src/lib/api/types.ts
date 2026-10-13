// TypeScript mirror of docs/contracts/api-gateway.openapi.yaml.
// If the contract changes, update this file in the same PR.

export type Role = "patient" | "clinician";

export interface LoginResponse {
  access_token: string;
  role: Role;
  user_id: string;
}

export interface Session {
  session_id: string;
  started_at: string; // ISO date-time
  camera_consent: boolean;
}

export type VisualStatus = "ok" | "uncertain" | "dropped" | "camera_off";

export interface FrameAck {
  visual_status: VisualStatus;
}

/** A label with its probability, e.g. ["sad", 0.46] */
export type LabelProb = [label: string, prob: number];

export interface ContextObject {
  visual: {
    status: VisualStatus;
    top2?: LabelProb[];
    stability?: number;
    window_s?: number;
    n_frames?: number;
  };
  text: { top2: LabelProb[] };
  agreement: "agree" | "disagree" | "n/a";
  tone_mode: "coach" | "supportive";
  note?: string;
}

/** data of a "token" event, e.g. {"text": "I hear you."} */
export interface TokenPayload {
  text: string;
}

export interface CrisisPayload {
  message: string;
  resources: { name: string; contact: string }[];
  review_flag_created: boolean;
}

export interface DonePayload {
  message_id: string;
  context: ContextObject;
}

/** One event from the streamed reply of POST /sessions/{id}/messages */
export type ChatEvent =
  | { type: "crisis"; data: CrisisPayload }
  | { type: "token"; data: string }
  | { type: "done"; data: DonePayload };
