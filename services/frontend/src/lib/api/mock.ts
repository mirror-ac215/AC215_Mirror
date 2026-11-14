// Fake api-gateway used while the real one doesn't exist (VITE_USE_MOCK_API=true).
// Every response has exactly the shape of the contract, so switching to the
// real gateway later changes nothing for the screens.

import { cannedReplies } from "@/lib/mirror-data";
import type {
  ChatEvent,
  ContextObject,
  FrameAck,
  LoginResponse,
  PatientSummary,
  ReviewFlagSummary,
  Role,
  Session,
  TrendPoint,
} from "./types";

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

// Demo-only stand-in. The real safety check runs in the api-gateway, never in the browser.
const DEMO_CRISIS_WORDS = ["kill myself", "end my life", "suicide", "hurt myself"];

let replyIndex = 0;

export async function login(email: string): Promise<LoginResponse> {
  await wait(300);
  const role: Role = email.startsWith("clinician.") ? "clinician" : "patient";
  return { access_token: "mock-token", role, user_id: role === "patient" ? "MR-1087" : "CL-01" };
}

export async function startSession(cameraConsent: boolean): Promise<Session> {
  await wait(200);
  return {
    session_id: `mock-${Date.now()}`,
    started_at: new Date().toISOString(),
    camera_consent: cameraConsent,
  };
}

export async function sendFrame(): Promise<FrameAck> {
  return {
    visual_status: "ok",
    top2: [
      ["neutral", 0.62],
      ["happy", 0.21],
    ],
  };
}

export async function sendMessage(
  text: string,
  onEvent: (event: ChatEvent) => void,
): Promise<void> {
  await wait(400);

  if (DEMO_CRISIS_WORDS.some((w) => text.toLowerCase().includes(w))) {
    onEvent({
      type: "crisis",
      data: {
        message:
          "It sounds like you're going through something really painful. You don't have to face it alone.",
        resources: [
          { name: "988 Suicide & Crisis Lifeline", contact: "call or text 988" },
          { name: "Emergency services", contact: "call 911 if you are in immediate danger" },
        ],
        review_flag_created: true,
      },
    });
    return;
  }

  const reply = cannedReplies[replyIndex % cannedReplies.length] ?? "Tell me more.";
  replyIndex += 1;
  for (const word of reply.split(" ")) {
    onEvent({ type: "token", data: `${word} ` });
    await wait(40);
  }

  const context: ContextObject = {
    visual: {
      status: "ok",
      top2: [
        ["sad", 0.46],
        ["neutral", 0.31],
      ],
      stability: 0.8,
      window_s: 10,
      n_frames: 8,
    },
    text: {
      top2: [
        ["sadness", 0.71],
        ["neutral", 0.12],
      ],
    },
    agreement: "agree",
    tone_mode: "supportive",
    note: "Estimates of expression, not facts about feelings.",
  };
  onEvent({ type: "done", data: { message_id: `mock-msg-${replyIndex}`, context } });
}

// --- Clinician dashboard (M4-01): same shapes as the gateway, same ids as services/db. ---

const DAY_MS = 24 * 60 * 60 * 1000;
const daysAgo = (days: number, hours = 0) =>
  new Date(Date.now() - days * DAY_MS - hours * 60 * 60 * 1000).toISOString();

const mockPatients: PatientSummary[] = [
  {
    patient_id: "00000000-0000-0000-0000-000000000201",
    display_name: "Alex Rivera",
    last_session_at: null,
    needs_review: false,
  },
  {
    patient_id: "00000000-0000-0000-0000-000000000202",
    display_name: "Bri Santos",
    last_session_at: daysAgo(1, 2),
    needs_review: true,
  },
  {
    patient_id: "00000000-0000-0000-0000-000000000203",
    display_name: "Casey Park",
    last_session_at: daysAgo(2, 5),
    needs_review: false,
  },
];

const mockFlags: Record<string, ReviewFlagSummary[]> = {
  "00000000-0000-0000-0000-000000000202": [
    { flag_id: "mock-flag-bri", created_at: daysAgo(3, 2), reviewed_at: null },
  ],
  "00000000-0000-0000-0000-000000000203": [
    { flag_id: "mock-flag-casey", created_at: daysAgo(8, 5), reviewed_at: daysAgo(7, 5) },
  ],
};

function mockTrend(patientId: string): TrendPoint[] {
  if (patientId !== "00000000-0000-0000-0000-000000000202") return [];
  const days: [number, string][] = [
    [13, "joy"],
    [11, "neutral"],
    [9, "sadness"],
    [6, "fear"],
    [3, "sadness"],
    [1, "neutral"],
  ];
  return days.flatMap(([day, label]) =>
    [0, 1, 2, 3].map((i): TrendPoint => {
      const ok = i === 0 || i === 2;
      return {
        ts: daysAgo(day, 2 - i / 10),
        visual_status: ok ? "ok" : i === 1 ? "uncertain" : "dropped",
        visual_top2: ok
          ? [
              [label === "joy" ? "happy" : "neutral", 0.6],
              ["sad", 0.2],
            ]
          : null,
        text_top2: [
          [i === 3 ? "neutral" : label, 0.55 + 0.1 * (i % 2)],
          ["neutral", 0.2],
        ],
        tone_mode: "supportive",
      };
    }),
  );
}

export async function listPatients(): Promise<PatientSummary[]> {
  await wait(250);
  return mockPatients.map((p) => ({
    ...p,
    needs_review: (mockFlags[p.patient_id] ?? []).some((f) => f.reviewed_at === null),
  }));
}

export async function getPatientTrend(patientId: string): Promise<TrendPoint[]> {
  await wait(250);
  return mockTrend(patientId);
}

export async function listReviewFlags(patientId: string): Promise<ReviewFlagSummary[]> {
  await wait(200);
  return mockFlags[patientId] ?? [];
}

export async function markFlagReviewed(flagId: string): Promise<void> {
  await wait(200);
  for (const flags of Object.values(mockFlags)) {
    for (const flag of flags) {
      if (flag.flag_id === flagId) flag.reviewed_at = new Date().toISOString();
    }
  }
}
