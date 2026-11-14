export const openingLine = "Hi, I'm glad you're here. Take your time.";

export const seededChat: { from: "bot" | "user"; text: string }[] = [
  { from: "bot", text: openingLine },
  { from: "user", text: "A bit overwhelmed, honestly." },
  {
    from: "bot",
    text: "That sounds heavy to carry. What has been asking the most of you lately?",
  },
  { from: "user", text: "Work mostly. I keep waking up at 4am thinking about it." },
];

export const cannedReplies = [
  "Thank you for telling me that. It makes sense you'd feel that way — what would a gentler version of today look like?",
  "I hear you. You don't have to sort it out all at once. Which part feels heaviest right now?",
  "That's a lot to hold on your own. Has anything, even something small, helped you settle recently?",
  "I'm listening. Take your time — we can stay with this for as long as you need.",
];
