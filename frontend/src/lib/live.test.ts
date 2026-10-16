import { describe, expect, it, vi } from "vitest";

import { ApiError } from "./api";
import { readEvents, subscribeLive, type LiveEvent } from "./live";

function body(...chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
}

describe("readEvents", () => {
  it("reads events split across chunks, skipping pings and retry", async () => {
    const events: LiveEvent[] = [];
    await readEvents(
      body(
        "retry: 3000\n\n: ping\n\n",
        'event: check_in\ndata: {"type":"check_in","mem',
        'ber":"m1"}\n\nevent: member\r\ndata: {"type":"member"}\r\n\r\n',
      ),
      (event) => events.push(event),
    );
    expect(events).toEqual([{ type: "check_in", member: "m1" }, { type: "member" }]);
  });
});

describe("subscribeLive", () => {
  it("reopens when the server ends the stream, and asks screens to resync", async () => {
    const events: LiveEvent[] = [];
    let opens = 0;
    const open = vi.fn(async () => {
      opens += 1;
      return new Response(opens === 1 ? body('data: {"type":"member"}\n\n') : body());
    });
    const stop = subscribeLive(open, (event) => events.push(event));
    await vi.waitFor(() => expect(opens).toBeGreaterThanOrEqual(2), { timeout: 3000 });
    stop();
    expect(events.slice(0, 2)).toEqual([{ type: "member" }, { type: "resync" }]);
  });

  it("stops for good once signed out", async () => {
    const open = vi.fn(async () => {
      throw new ApiError(401, "session_ended", "Signed out");
    });
    subscribeLive(open, () => undefined);
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(open).toHaveBeenCalledTimes(1);
  });
});
