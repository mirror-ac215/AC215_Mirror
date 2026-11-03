export type ChatMessage = { from: "bot" | "user"; text: string };

export const NO_REPLY = "Sorry, I couldn't put a reply together just now. Please try again.";

/**
 * After a reply stream ends: if Mirror's bubble is still empty (no token and no crisis
 * event arrived), show a short fallback instead of a blank answer.
 */
export function fillEmptyReply(messages: ChatMessage[]): ChatMessage[] {
  const last = messages[messages.length - 1];
  if (last?.from !== "bot" || last.text.trim()) return messages;
  return [...messages.slice(0, -1), { from: "bot", text: NO_REPLY }];
}
