/**
 * A gym's address from whatever the member has: the poster's QR
 * ("https://app.gymbhai.com/fitness-zone?b=..."), the welcome SMS link,
 * gymbhai://fitness-zone, or the address typed in.
 */
const SLUG = /^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$/;

export interface GymLink {
  slug: string;
  /** What comes after the gym in the link: "join", "renew"... */
  rest: string[];
}

export function parseGymLink(input: string): GymLink | null {
  const text = input.trim();
  if (!text) return null;
  let path: string;
  const scheme = /^gymbhai:\/\/(.*)$/i.exec(text);
  if (scheme) {
    path = scheme[1];
  } else if (/^https?:\/\//i.test(text)) {
    try {
      path = new URL(text).pathname;
    } catch {
      return null;
    }
  } else {
    // Typed: "app.gymbhai.com/fitness-zone", or just "fitness-zone".
    path = text.replace(/^[a-z0-9.-]+\.[a-z]{2,}(?::\d+)?\//i, "");
  }
  const parts = path
    .split(/[?#]/)[0]
    .split("/")
    .filter(Boolean)
    .map((part) => decodeURIComponent(part).toLowerCase());
  const [slug, ...rest] = parts;
  if (!slug || !SLUG.test(slug)) return null;
  return { slug, rest };
}
