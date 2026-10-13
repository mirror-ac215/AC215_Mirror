// Turns a Server-Sent Events text stream into ChatEvents. Kept separate from
// client.ts so it can be unit-tested without a network.

import type { ChatEvent, TokenPayload } from "./types";

export function createSseParser(onEvent: (event: ChatEvent) => void) {
  let buffer = "";

  function handleBlock(block: string) {
    let type = "";
    const dataLines: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) type = line.slice(6).trim();
      else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
    }
    const data = dataLines.join("\n"); // the SSE standard joins multiple data lines with newlines
    if (type === "token") onEvent({ type, data: (JSON.parse(data) as TokenPayload).text });
    else if (type === "crisis" || type === "done") onEvent({ type, data: JSON.parse(data) });
  }

  return {
    /** Add the next chunk of text from the network. */
    push(chunk: string) {
      // Normalise line endings on the WHOLE buffer, not just the new chunk: a "\r\n"
      // can arrive split, with "\r" ending one chunk and "\n" starting the next.
      buffer = (buffer + chunk).replaceAll("\r\n", "\n");
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() ?? ""; // keep an unfinished block for the next chunk
      blocks.forEach(handleBlock);
    },
    /** The stream ended: handle a last event that had no blank line after it. */
    flush() {
      if (buffer.trim()) handleBlock(buffer.replace(/\r$/, ""));
      buffer = "";
    },
  };
}
