/**
 * Live updates over a WebSocket (PLAN.md §17.3; the server is
 * backend/app/api/routes/member_socket.py).
 *
 * - Signs in with its first message; the token never goes in the URL.
 * - Renews the token on the same socket a minute before it runs out.
 * - Answers the server's pings; reconnects with backoff after any close,
 *   at once when the app comes to the front or the internet returns.
 * - After every (re)connect, screens re-read: events may have been missed.
 */
import type { MemberLiveType } from "@shared/types";

export const CLOSE_UNAUTHORIZED = 4401;
export const BACKOFF_MS = [1_000, 2_000, 5_000, 10_000, 30_000];
/** Renew the token this long before it runs out. */
const RENEW_BEFORE_MS = 60_000;

export interface LiveOptions {
  url: string;
  /** A token good for a while; null when signed out. May throw when offline. */
  getToken: (force: boolean) => Promise<{ token: string; expiresAt: number } | null>;
  onEvent: (type: MemberLiveType) => void;
  /** Connected (again): re-read what's on screen. */
  onReady: () => void;
  /** For tests. */
  createSocket?: (url: string) => WebSocket;
  setTimer?: typeof setTimeout;
  clearTimer?: typeof clearTimeout;
}

export type LiveState = "connecting" | "open" | "closed";

export class LiveSocket {
  private socket: WebSocket | null = null;
  private stopped = true;
  private attempt = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private renewTimer: ReturnType<typeof setTimeout> | null = null;
  private forceRefresh = false;
  /** Fetching a token: a nudge now must not open a second socket. */
  private opening = false;
  state: LiveState = "closed";

  constructor(private readonly options: LiveOptions) {}

  start() {
    if (!this.stopped) return;
    this.stopped = false;
    this.attempt = 0;
    void this.connect();
  }

  stop() {
    this.stopped = true;
    this.clearTimers();
    const socket = this.socket;
    this.socket = null;
    this.state = "closed";
    socket?.close(1000);
  }

  /** The app came to the front, or the internet came back: don't wait. */
  nudge() {
    if (this.stopped || this.socket || this.opening) return;
    this.attempt = 0;
    this.clearTimers();
    void this.connect();
  }

  private timer(fn: () => void, ms: number) {
    return (this.options.setTimer ?? setTimeout)(fn, ms);
  }

  private clearTimers() {
    const clear = this.options.clearTimer ?? clearTimeout;
    if (this.reconnectTimer) clear(this.reconnectTimer);
    if (this.renewTimer) clear(this.renewTimer);
    this.reconnectTimer = this.renewTimer = null;
  }

  private async connect() {
    if (this.stopped || this.socket || this.opening) return;
    this.state = "connecting";
    this.opening = true;
    let auth: Awaited<ReturnType<LiveOptions["getToken"]>>;
    try {
      auth = await this.options.getToken(this.forceRefresh);
    } catch {
      return this.retryLater(); // offline: no token to be had
    } finally {
      this.opening = false;
    }
    this.forceRefresh = false;
    if (!auth) return this.stop(); // signed out
    if (this.stopped) return;

    const socket = (this.options.createSocket ?? ((url) => new WebSocket(url)))(
      this.options.url,
    );
    this.socket = socket;
    socket.onopen = () => {
      socket.send(JSON.stringify({ type: "auth", token: auth.token }));
    };
    socket.onmessage = (message) => {
      if (socket !== this.socket) return;
      let data: { type?: string };
      try {
        data = JSON.parse(String(message.data));
      } catch {
        return;
      }
      if (data.type === "ping") {
        socket.send(JSON.stringify({ type: "pong" }));
      } else if (data.type === "ready") {
        this.attempt = 0;
        this.state = "open";
        this.scheduleRenewal(auth.expiresAt);
        this.options.onReady();
      } else if (data.type) {
        this.options.onEvent(data.type as MemberLiveType);
      }
    };
    socket.onclose = (event) => {
      if (socket !== this.socket) return;
      this.socket = null;
      this.state = "closed";
      if (this.renewTimer) (this.options.clearTimer ?? clearTimeout)(this.renewTimer);
      this.renewTimer = null;
      // The token ran out or was refused: a fresh one next time.
      if (event.code === CLOSE_UNAUTHORIZED) this.forceRefresh = true;
      this.retryLater();
    };
    socket.onerror = () => {
      // onclose follows and does the rest.
    };
  }

  private scheduleRenewal(expiresAt: number) {
    const wait = Math.max(5_000, expiresAt - Date.now() - RENEW_BEFORE_MS);
    this.renewTimer = this.timer(async () => {
      const socket = this.socket;
      if (!socket || this.stopped) return;
      try {
        const fresh = await this.options.getToken(true);
        if (!fresh || socket !== this.socket) return;
        socket.send(JSON.stringify({ type: "auth", token: fresh.token }));
        this.scheduleRenewal(fresh.expiresAt);
      } catch {
        // Offline: the server closes it at expiry and we reconnect later.
      }
    }, wait);
  }

  private retryLater() {
    if (this.stopped) return;
    const delay = BACKOFF_MS[Math.min(this.attempt, BACKOFF_MS.length - 1)];
    this.attempt += 1;
    this.reconnectTimer = this.timer(() => {
      this.reconnectTimer = null;
      void this.connect();
    }, delay);
  }
}
