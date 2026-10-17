/**
 * The server's time, from the Date header on every answer (PLAN.md §17.2, 7).
 *
 * The QR changes every 30 seconds and the door allows one window either side,
 * so a phone whose clock is a few minutes off would show codes the door
 * refuses. The QR is drawn at `serverNow()` instead of the phone's time.
 */
import AsyncStorage from "@react-native-async-storage/async-storage";

const STORAGE_KEY = "gymbhai.clockOffset";

let offsetMs = 0;
let known = false;

/** Ignore differences this small: Date has one-second resolution anyway. */
const NOISE_MS = 2_000;

/**
 * One answer's Date header, with when the request left and the answer came.
 * The server stamped it somewhere in between; the midpoint is the best guess.
 */
export function observe(dateHeader: string | null, sentAt: number, receivedAt: number) {
  if (!dateHeader) return;
  const server = Date.parse(dateHeader);
  if (Number.isNaN(server)) return;
  // Date is whole seconds, rounded down: add half a second.
  const offset = server + 500 - (sentAt + receivedAt) / 2;
  if (!known || Math.abs(offset - offsetMs) > NOISE_MS) {
    offsetMs = Math.abs(offset) < NOISE_MS ? 0 : offset;
    known = true;
    // Kept for the next launch: the QR may be needed offline, at the door.
    AsyncStorage.setItem(STORAGE_KEY, String(Math.round(offsetMs))).catch(() => {});
  }
}

/** The last known difference, until this launch's first answer. */
export async function restoreClock(): Promise<void> {
  try {
    const saved = Number(await AsyncStorage.getItem(STORAGE_KEY));
    if (!known && Number.isFinite(saved)) offsetMs = saved;
  } catch {
    // Nothing saved: the phone's own time.
  }
}

export function serverNow(): number {
  return Date.now() + offsetMs;
}

export function clockOffset(): number {
  return offsetMs;
}

/** For tests. */
export function resetClock(offset = 0) {
  offsetMs = offset;
  known = offset !== 0;
}
