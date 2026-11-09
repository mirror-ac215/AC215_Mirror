export type EmotionTone = "calm" | "anxious" | "sad" | "lowmood" | "neutral" | "reflective";

export const toneClass: Record<EmotionTone, string> = {
  calm: "bg-calm text-[#4b7a62]",
  anxious: "bg-anxious text-[#96702f]",
  sad: "bg-sad text-[#5a6a92]",
  lowmood: "bg-lowmood text-[#a3675b]",
  neutral: "bg-neutral text-muted-ink",
  reflective: "bg-reflective text-[#7b6aa8]",
};

export const toneLabel: Record<EmotionTone, string> = {
  calm: "calm",
  anxious: "anxious",
  sad: "sad",
  lowmood: "low mood",
  neutral: "neutral",
  reflective: "reflective",
};

export type Patient = {
  id: string;
  name: string;
  lastActive: string;
  tone: EmotionTone;
  needsReview?: boolean;
  sessionsThisMonth: number;
  engagement: string;
  openItems: number;
  avgMood: string;
};

export const patients: Patient[] = [
  {
    id: "MR-1042",
    name: "Amara Okafor",
    lastActive: "2 hours ago",
    tone: "reflective",
    sessionsThisMonth: 6,
    engagement: "High",
    openItems: 0,
    avgMood: "Steady",
  },
  {
    id: "MR-1087",
    name: "Daniel Reyes",
    lastActive: "Yesterday",
    tone: "lowmood",
    needsReview: true,
    sessionsThisMonth: 8,
    engagement: "Moderate",
    openItems: 1,
    avgMood: "Neutral",
  },
  {
    id: "MR-1113",
    name: "Sofia Lindqvist",
    lastActive: "3 days ago",
    tone: "calm",
    sessionsThisMonth: 4,
    engagement: "Steady",
    openItems: 0,
    avgMood: "Positive",
  },
  {
    id: "MR-1156",
    name: "Jonah Bennett",
    lastActive: "5 hours ago",
    tone: "anxious",
    sessionsThisMonth: 7,
    engagement: "High",
    openItems: 0,
    avgMood: "Variable",
  },
  {
    id: "MR-1190",
    name: "Priya Nair",
    lastActive: "Last week",
    tone: "sad",
    sessionsThisMonth: 3,
    engagement: "Low",
    openItems: 0,
    avgMood: "Subdued",
  },
  {
    id: "MR-1204",
    name: "Tomas Alvarez",
    lastActive: "Today",
    tone: "neutral",
    sessionsThisMonth: 5,
    engagement: "Steady",
    openItems: 0,
    avgMood: "Neutral",
  },
];

export const moodTrend = [
  { session: "S1", valence: 0.42, low: false },
  { session: "S2", valence: 0.38, low: false },
  { session: "S3", valence: 0.4, low: false },
  { session: "S4", valence: 0.31, low: false },
  { session: "S5", valence: 0.27, low: false },
  { session: "S6", valence: 0.24, low: false },
  { session: "S7", valence: 0.11, low: true },
  { session: "S8", valence: 0.21, low: false },
];

export const recentSessions: { date: string; length: string; tones: EmotionTone[] }[] = [
  { date: "Sep 24, 2026", length: "18 min", tones: ["lowmood", "reflective"] },
  { date: "Sep 20, 2026", length: "9 min", tones: ["anxious"] },
  { date: "Sep 16, 2026", length: "22 min", tones: ["sad", "calm"] },
  { date: "Sep 11, 2026", length: "15 min", tones: ["neutral", "reflective"] },
  { date: "Sep 6, 2026", length: "20 min", tones: ["calm"] },
];

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
