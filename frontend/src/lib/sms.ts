/**
 * How many SMS a text costs — the same rules as backend/app/core/sms_text.py.
 * Plain English fits 160 characters; one Nepali letter makes the whole
 * message Unicode, which fits 70 (PLAN.md §10).
 */
const GSM = new Set(
  "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?" +
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà",
);
const GSM_EXTENDED = new Set("^{}\\[~]|€");

export function isGsm(text: string): boolean {
  return [...text].every((ch) => GSM.has(ch) || GSM_EXTENDED.has(ch));
}

export function smsParts(text: string): number {
  if (!text) return 0;
  let length: number;
  let single: number;
  let part: number;
  if (isGsm(text)) {
    length = [...text].reduce((n, ch) => n + (GSM_EXTENDED.has(ch) ? 2 : 1), 0);
    [single, part] = [160, 153];
  } else {
    length = text.length; // UTF-16 code units, as the gateways count
    [single, part] = [70, 67];
  }
  return length <= single ? 1 : Math.ceil(length / part);
}
