import { describe, expect, it } from "vitest";
import { ApiError } from "@/lib/api/client";
import type { TrendPoint } from "@/lib/api/types";
import {
  confidence,
  dailyReadings,
  faceWords,
  relativeDay,
  retryUnlessRefused,
  sortFlags,
  textWords,
} from "./clinician";

const point = (ts: string, extra: Partial<TrendPoint> = {}): TrendPoint => ({
  ts,
  visual_status: "camera_off",
  text_top2: [["neutral", 0.6]],
  tone_mode: "supportive",
  ...extra,
});

describe("soft wording (MS1 feedback)", () => {
  const banned = /anxious|depress|low mood|angry|afraid|scared|diagnos/i;

  it("describes every face label as an observable expression, never a feeling", () => {
    for (const label of ["happy", "neutral", "sad", "angry", "disgust", "fear", "surprise"]) {
      expect(faceWords(label)).not.toMatch(banned);
      expect(faceWords(label)).toMatch(/looking|smiling/);
    }
    expect(faceWords("angry")).toBe("tense-looking");
  });

  it("describes every text label as wording, never the person", () => {
    for (const label of ["joy", "neutral", "surprise", "sadness", "fear", "anger", "disgust"]) {
      expect(textWords(label)).not.toMatch(banned);
      expect(textWords(label)).toMatch(/wording$/);
    }
  });

  it("falls back to 'unclear' for a label it does not know", () => {
    expect(faceWords("contempt")).toBe("unclear expression");
    expect(textWords("love")).toBe("unclear wording");
  });
});

describe("confidence", () => {
  it("is always low with fewer than 3 readings, however sure the model is", () => {
    expect(confidence(0.95, 2)).toBe("low confidence");
  });

  it("follows the average probability once there are enough readings", () => {
    expect(confidence(0.45, 5)).toBe("low confidence");
    expect(confidence(0.6, 5)).toBe("medium confidence");
    expect(confidence(0.8, 5)).toBe("higher confidence");
  });
});

describe("dailyReadings", () => {
  it("groups by day, oldest first, and splits wording into lighter and heavier", () => {
    const days = dailyReadings([
      point("2026-11-10T15:00:00", { text_top2: [["sadness", 0.8]] }),
      point("2026-11-09T15:00:00", { text_top2: [["joy", 0.7]] }),
      point("2026-11-10T15:05:00", { text_top2: [["neutral", 0.8]] }),
      point("2026-11-10T15:10:00", { text_top2: [["fear", 0.8]] }),
    ]);
    expect(days.map((d) => d.day)).toEqual(["2026-11-09", "2026-11-10"]);
    expect(days[1]!.textReadings).toBe(3);
    expect(days[1]!.heavierShare).toBeCloseTo(2 / 3);
    expect(days[1]!.lighterShare).toBeCloseTo(1 / 3);
    expect(days[1]!.textConfidence).toBe("higher confidence");
    expect(days[0]!.textConfidence).toBe("low confidence");
  });

  it("uses only steady (gate ok) face readings, and says when the camera was off", () => {
    const [day] = dailyReadings([
      point("2026-11-10T15:00:00", { visual_status: "ok", visual_top2: [["sad", 0.6]] }),
      point("2026-11-10T15:01:00", { visual_status: "ok", visual_top2: [["sad", 0.6]] }),
      point("2026-11-10T15:02:00", { visual_status: "uncertain", visual_top2: [["happy", 0.9]] }),
    ]);
    expect(day!.faceEstimate).toBe("downcast-looking");
    expect(day!.steadyFaceReadings).toBe(2);
    expect(day!.windows).toBe(3);
    expect(day!.cameraOff).toBe(false);

    const [off] = dailyReadings([point("2026-11-11T09:00:00")]);
    expect(off!.cameraOff).toBe(true);
    expect(off!.faceEstimate).toBeNull();
    expect(off!.faceConfidence).toBeNull();
  });

  it("returns nothing for a patient with no sessions", () => {
    expect(dailyReadings([])).toEqual([]);
  });
});

describe("sortFlags and relativeDay", () => {
  it("puts open flags first, newest first", () => {
    const sorted = sortFlags([
      {
        flag_id: "old-done",
        created_at: "2026-11-01T00:00:00Z",
        reviewed_at: "2026-11-02T00:00:00Z",
      },
      { flag_id: "old-open", created_at: "2026-11-03T00:00:00Z", reviewed_at: null },
      { flag_id: "new-open", created_at: "2026-11-05T00:00:00Z", reviewed_at: null },
    ]);
    expect(sorted.map((f) => f.flag_id)).toEqual(["new-open", "old-open", "old-done"]);
  });

  it("says today, yesterday or N days ago", () => {
    const now = new Date(2026, 10, 14, 12);
    expect(relativeDay(null, now)).toBe("No sessions yet");
    expect(relativeDay(new Date(2026, 10, 14, 8).toISOString(), now)).toBe("today");
    expect(relativeDay(new Date(2026, 10, 13, 23).toISOString(), now)).toBe("yesterday");
    expect(relativeDay(new Date(2026, 10, 10, 9).toISOString(), now)).toBe("4 days ago");
  });
});

describe("retryUnlessRefused", () => {
  it("never retries a refusal (401, 403, 404)", () => {
    for (const status of [401, 403, 404]) {
      expect(retryUnlessRefused(0, new ApiError("/clinician/patients", status))).toBe(false);
    }
  });

  it("retries network and server errors twice", () => {
    expect(retryUnlessRefused(0, new ApiError("/clinician/patients", 503))).toBe(true);
    expect(retryUnlessRefused(1, new TypeError("Failed to fetch"))).toBe(true);
    expect(retryUnlessRefused(2, new TypeError("Failed to fetch"))).toBe(false);
  });
});
