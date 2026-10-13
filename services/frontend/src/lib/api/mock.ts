// Fake api-gateway used while the real one doesn't exist (VITE_USE_MOCK_API=true).
// Every response has exactly the shape of the contract, so switching to the
// real gateway later changes nothing for the screens.

import { cannedReplies } from "@/lib/mirror-data";
import type { ChatEvent, ContextObject, FrameAck, LoginResponse, Role, Session } from "./types";

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

// Demo-only stand-in. The real safety check runs in the api-gateway, never in the browser.
const DEMO_CRISIS_WORDS = ["kill myself", "end my life", "suicide", "hurt myself"];

let replyIndex = 0;

export async function login(role: Role): Promise<LoginResponse> {
  await wait(300);
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
  return { visual_status: "ok" };
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
        resources: [{ name: "988 Suicide & Crisis Lifeline", contact: "call or text 988" }],
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
