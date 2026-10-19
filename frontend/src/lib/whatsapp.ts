/**
 * WhatsApp from the desk's own phone (PLAN.md §18.5): a link that opens a
 * chat with the member, the message already written. It goes from that
 * phone's WhatsApp when someone presses Send: free, and nothing passes us.
 */

/** Nepali mobile numbers are stored as 98XXXXXXXX; WhatsApp wants 97798…. */
export function whatsappLink(phone: string, text?: string): string {
  const digits = phone.replace(/\D/g, "");
  const international = digits.length === 10 ? `977${digits}` : digits;
  const base = `https://wa.me/${international}`;
  return text ? `${base}?text=${encodeURIComponent(text)}` : base;
}
