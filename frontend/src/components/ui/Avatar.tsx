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
      <img
        src={url}
        alt=""
        className={`${size} shrink-0 rounded-full object-cover ring-1 ring-hairline`}
      />
    );
  }
  const initials = name
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase())
    .join("");
  return (
    <span
      className={`${size} flex shrink-0 items-center justify-center rounded-full bg-linear-to-br from-brand-500 to-brand-700 text-sm font-semibold text-white ring-1 ring-brand-900/10`}
    >
      {initials}
    </span>
  );
}
