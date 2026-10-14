import { describe, expect, it } from "vitest";
import { createSseParser } from "./sse";
import type { ChatEvent } from "./types";

function collect() {
  const events: ChatEvent[] = [];
  const parser = createSseParser((e) => events.push(e));
  return { events, parser };
}

describe("createSseParser", () => {
  it("handles a CRLF line ending split across two chunks", () => {
    const { events, parser } = collect();
    parser.push('event: token\r\ndata: {"text":"Hi"}\r');
    parser.push('\n\r\nevent: done\r\ndata: {"message_id":"m1"}\r\n\r\n');
    expect(events).toEqual([
      { type: "token", data: "Hi" },
      { type: "done", data: { message_id: "m1" } },
    ]);
  });

  it("handles crisis events", () => {
    const { events, parser } = collect();
    parser.push('event: crisis\ndata: {"type":"crisis"}\n\n');
    expect(events[0]?.type).toBe("crisis");
  });

  it("flushes a last event that has no blank line after it", () => {
    const { events, parser } = collect();
    parser.push('event: done\ndata: {"message_id":"m2"}');
    expect(events).toEqual([]);
    parser.flush();
    expect(events).toEqual([{ type: "done", data: { message_id: "m2" } }]);
  });
});
