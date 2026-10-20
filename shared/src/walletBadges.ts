import type { AccountKind } from "./types";

/**
 * Each wallet as a letter in its own colour, on Renew (PLAN.md §5.2): we
 * bundle none of their logos.
 */
export const WALLET_BADGES: Record<
  AccountKind,
  { letter: string; color: string }
> = {
  esewa: { letter: "e", color: "#41a124" },
  khalti: { letter: "K", color: "#5c2d91" },
  fonepay: { letter: "F", color: "#c8102e" },
  bank: { letter: "₨", color: "#334155" },
  other: { letter: "•", color: "#334155" },
};
