// Turns the gateway's aggregate readings into what a clinician sees (M4-01).
// MS1 feedback: describe what the models estimated, never a feeling or a diagnosis
// ("tense-looking, low confidence", not "anxious"), and show confidence with every estimate.

import { ApiError } from "@/lib/api/client";
import type { LabelProb, ReviewFlagSummary, TrendPoint } from "@/lib/api/types";

/**
 * React Query retry rule for clinician calls: a 4xx (expired login, not your patient)
 * won't change on retry, so show it at once; retry network and 5xx errors twice.
 */
export function retryUnlessRefused(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false;
  return failureCount < 2;
}

/** Shown next to every estimate on the dashboard. */
export const ESTIMATE_NOTE = "An estimate, not a feeling.";

/** Face model labels (cv-service) in neutral, observable words. */
const FACE_WORDS: Record<string, string> = {
  happy: "smiling",
  neutral: "neutral-looking",
  sad: "downcast-looking",
  angry: "tense-looking",
  disgust: "tense-looking",
  fear: "tense-looking",
  surprise: "surprised-looking",
};

/** Text model labels (j-hartmann, D-003) describe the wording, not the person. */
const TEXT_WORDS: Record<string, string> = {
  joy: "lighter wording",
  neutral: "neutral wording",
  surprise: "surprised wording",
  sadness: "heavier wording",
  sad: "heavier wording",
  fear: "worried wording",
  anger: "frustrated wording",
  angry: "frustrated wording",
  disgust: "frustrated wording",
};

/** Text labels that count as "heavier" on the day-by-day chart. */
const HEAVIER_TEXT = new Set(["sadness", "sad", "fear", "anger", "angry", "disgust"]);

export function faceWords(label: string): string {
  return FACE_WORDS[label] ?? "unclear expression";
}

export function textWords(label: string): string {
  return TEXT_WORDS[label] ?? "unclear wording";
}

export type Confidence = "low confidence" | "medium confidence" | "higher confidence";

/**
 * Confidence of a group of readings, from their average top probability and how many there are.
 * Fewer than 3 readings is always low confidence: one message says little about a day.
 */
export function confidence(averageProbability: number, readings: number): Confidence {
  if (readings < 3 || averageProbability < 0.5) return "low confidence";
  if (averageProbability < 0.7) return "medium confidence";
  return "higher confidence";
}

function top(readings: LabelProb[] | null | undefined): LabelProb | null {
  return readings && readings.length > 0 ? readings[0]! : null;
}

export interface DayReading {
  /** Local calendar day, YYYY-MM-DD. */
  day: string;
  /** Short label for the chart axis, e.g. "Nov 3". */
  label: string;
  /** Messages with a text reading that day. */
  textReadings: number;
  /** Share of those messages whose wording read as heavier (0-1). */
  heavierShare: number;
  lighterShare: number;
  textConfidence: Confidence;
  /** Windows where the gate passed a steady face reading, out of all windows that day. */
  steadyFaceReadings: number;
  windows: number;
  cameraOff: boolean;
  /** Most common steady face estimate that day, in neutral words, or null. */
  faceEstimate: string | null;
  faceConfidence: Confidence | null;
}

function localDay(iso: string): string {
  const d = new Date(iso);
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${month}-${day}`;
}

function shortLabel(day: string): string {
  const [y, m, d] = day.split("-").map(Number) as [number, number, number];
  return new Date(y, m - 1, d).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

const average = (values: number[]) =>
  values.length ? values.reduce((sum, v) => sum + v, 0) / values.length : 0;

/** Group trend points by day, oldest first. */
export function dailyReadings(points: TrendPoint[]): DayReading[] {
  const byDay = new Map<string, TrendPoint[]>();
  for (const point of points) {
    const day = localDay(point.ts);
    byDay.set(day, [...(byDay.get(day) ?? []), point]);
  }

  return [...byDay.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([day, dayPoints]) => {
      const text = dayPoints.map((p) => top(p.text_top2)).filter((r): r is LabelProb => !!r);
      const heavier = text.filter(([label]) => HEAVIER_TEXT.has(label)).length;

      const steady = dayPoints
        .filter((p) => p.visual_status === "ok")
        .map((p) => top(p.visual_top2))
        .filter((r): r is LabelProb => !!r);
      const counts = new Map<string, number>();
      for (const [label] of steady) {
        const words = faceWords(label);
        counts.set(words, (counts.get(words) ?? 0) + 1);
      }
      const faceEstimate =
        [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))[0]?.[0] ??
        null;

      return {
        day,
        label: shortLabel(day),
        textReadings: text.length,
        heavierShare: text.length ? heavier / text.length : 0,
        lighterShare: text.length ? (text.length - heavier) / text.length : 0,
        textConfidence: confidence(average(text.map(([, p]) => p)), text.length),
        steadyFaceReadings: steady.length,
        windows: dayPoints.length,
        cameraOff: dayPoints.every((p) => p.visual_status === "camera_off"),
        faceEstimate,
        faceConfidence: steady.length
          ? confidence(average(steady.map(([, p]) => p)), steady.length)
          : null,
      };
    });
}

/** Open flags first (newest first), then reviewed ones (newest first). */
export function sortFlags(flags: ReviewFlagSummary[]): ReviewFlagSummary[] {
  return [...flags].sort((a, b) => {
    const openA = a.reviewed_at === null ? 0 : 1;
    const openB = b.reviewed_at === null ? 0 : 1;
    return openA - openB || b.created_at.localeCompare(a.created_at);
  });
}

/** "today", "yesterday", "3 days ago", or a date for anything older than two weeks. */
export function relativeDay(iso: string | null, now: Date = new Date()): string {
  if (!iso) return "No sessions yet";
  const then = new Date(iso);
  const startOf = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const days = Math.round((startOf(now) - startOf(then)) / (24 * 60 * 60 * 1000));
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 14) return `${days} days ago`;
  return then.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export function dateTime(iso: string): string {
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}
