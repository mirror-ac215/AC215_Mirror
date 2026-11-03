import { describe, expect, it } from "vitest";
import { fillEmptyReply, NO_REPLY, type ChatMessage } from "./chat";

const user: ChatMessage = { from: "user", text: "hi" };

describe("fillEmptyReply", () => {
  it("replaces an empty reply bubble with the fallback", () => {
    expect(fillEmptyReply([user, { from: "bot", text: "  " }])).toEqual([
      user,
      { from: "bot", text: NO_REPLY },
    ]);
  });

  it("keeps a reply that has text", () => {
    const messages: ChatMessage[] = [user, { from: "bot", text: "I hear you. " }];
    expect(fillEmptyReply(messages)).toBe(messages);
  });

  it("leaves a crisis turn alone (its bubble was already removed)", () => {
    const messages = [user];
    expect(fillEmptyReply(messages)).toBe(messages);
  });
});
