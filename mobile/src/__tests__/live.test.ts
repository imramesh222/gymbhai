/** The WebSocket client (PLAN.md §17.3) against a fake socket. */
import { BACKOFF_MS, CLOSE_UNAUTHORIZED, LiveSocket } from "@/lib/live";

class FakeSocket {
  sent: unknown[] = [];
  closedWith: number | null = null;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: ((event: { code: number }) => void) | null = null;
  onerror: (() => void) | null = null;
  send(data: string) {
    this.sent.push(JSON.parse(data));
  }
  close(code: number) {
    this.closedWith = code;
  }
  // The server's side.
  open() {
    this.onopen?.();
  }
  say(message: object) {
    this.onmessage?.({ data: JSON.stringify(message) });
  }
  drop(code = 1006) {
    this.onclose?.({ code });
  }
}

function setUp() {
  const sockets: FakeSocket[] = [];
  const tokens: boolean[] = [];
  const events: string[] = [];
  let ready = 0;
  let n = 0;
  const live = new LiveSocket({
    url: "ws://test/api/v1/m/ws",
    getToken: async (force) => {
      tokens.push(force);
      n += 1;
      return { token: `token-${n}`, expiresAt: Date.now() + 15 * 60_000 };
    },
    onEvent: (type) => events.push(type),
    onReady: () => (ready += 1),
    createSocket: () => {
      const socket = new FakeSocket();
      sockets.push(socket);
      return socket as unknown as WebSocket;
    },
  });
  return { live, sockets, tokens, events, ready: () => ready };
}

const tick = () => new Promise((resolve) => setImmediate(resolve));

beforeEach(() => jest.useFakeTimers({ doNotFake: ["setImmediate"] }));
afterEach(() => jest.useRealTimers());

test("signs in with its first message, answers pings, passes events on", async () => {
  const { live, sockets, events, ready } = setUp();
  live.start();
  await tick();
  const socket = sockets[0];
  socket.open();
  expect(socket.sent[0]).toEqual({ type: "auth", token: "token-1" });
  socket.say({ type: "ready" });
  expect(ready()).toBe(1);
  socket.say({ type: "ping" });
  expect(socket.sent[1]).toEqual({ type: "pong" });
  socket.say({ type: "payment_request", member: "m" });
  socket.say({ type: "notice" });
  expect(events).toEqual(["payment_request", "notice"]);
  live.stop();
  expect(socket.closedWith).toBe(1000);
});

test("renews its token on the same socket before it runs out", async () => {
  const { live, sockets, tokens } = setUp();
  live.start();
  await tick();
  sockets[0].open();
  sockets[0].say({ type: "ready" });
  await jest.advanceTimersByTimeAsync(14 * 60_000 + 1);
  expect(tokens).toEqual([false, true]);
  expect(sockets).toHaveLength(1);
  expect(sockets[0].sent.at(-1)).toEqual({ type: "auth", token: "token-2" });
  live.stop();
});

test("reconnects with backoff, and with a fresh token after 4401", async () => {
  const { live, sockets, tokens, ready } = setUp();
  live.start();
  await tick();
  sockets[0].open();
  sockets[0].say({ type: "ready" });
  sockets[0].drop(CLOSE_UNAUTHORIZED);
  await jest.advanceTimersByTimeAsync(BACKOFF_MS[0] - 1);
  expect(sockets).toHaveLength(1);
  await jest.advanceTimersByTimeAsync(1);
  expect(sockets).toHaveLength(2);
  expect(tokens).toEqual([false, true]);
  sockets[1].open();
  sockets[1].say({ type: "ready" });
  expect(ready()).toBe(2); // screens re-read after the reconnect
  live.stop();
});

test("a nudge reconnects now, not after the backoff", async () => {
  const { live, sockets } = setUp();
  live.start();
  await tick();
  sockets[0].drop();
  live.nudge();
  await tick();
  expect(sockets).toHaveLength(2);
  live.nudge(); // already connecting: no third socket
  await tick();
  expect(sockets).toHaveLength(2);
  live.stop();
});

test("signed out: stops instead of retrying", async () => {
  const sockets: FakeSocket[] = [];
  const live = new LiveSocket({
    url: "ws://test",
    getToken: async () => null,
    onEvent: () => {},
    onReady: () => {},
    createSocket: () => {
      const socket = new FakeSocket();
      sockets.push(socket);
      return socket as unknown as WebSocket;
    },
  });
  live.start();
  await tick();
  await jest.advanceTimersByTimeAsync(60_000);
  expect(sockets).toHaveLength(0);
});
