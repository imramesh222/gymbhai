export function Avatar({
  name,
  url,
  size = "size-10",
}: {
  name: string;
  url: string | null;
  size?: string;
}) {
  if (url) {
    // Signed, expiring URLs from our API: next/image's optimiser would cache
    // them past expiry, so a plain <img> is the right tool here.
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img src={url} alt="" className={`${size} shrink-0 rounded-full object-cover`} />
    );
  }
  const initials = name
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase())
    .join("");
  return (
    <span
      className={`${size} flex shrink-0 items-center justify-center rounded-full bg-brand-100 text-sm font-semibold text-brand-700`}
    >
      {initials}
    </span>
  );
}
