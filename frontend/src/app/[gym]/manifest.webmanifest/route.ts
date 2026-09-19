/**
 * Each gym's own web manifest (PLAN.md §3), so "Add to Home Screen" installs
 * an icon with that gym's name and logo.
 */
const API = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

export async function GET(
  _: Request,
  { params }: { params: Promise<{ gym: string }> },
) {
  const { gym: slug } = await params;
  const response = await fetch(`${API}/api/v1/m/${encodeURIComponent(slug)}/gym`, {
    cache: "no-store",
  }).catch(() => null);
  if (!response?.ok) return new Response("Not found", { status: 404 });
  const gym = (await response.json()) as {
    name: string;
    brand_color: string | null;
    logo_url: string | null;
  };
  const icons = gym.logo_url
    ? [{ src: gym.logo_url, sizes: "512x512", type: "image/png", purpose: "any" }]
    : [
        { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
        { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
      ];
  return Response.json(
    {
      name: gym.name,
      short_name: gym.name.slice(0, 12),
      start_url: `/${slug}`,
      scope: `/${slug}`,
      display: "standalone",
      background_color: "#f8fafc",
      theme_color: gym.brand_color ?? "#1d5fd1",
      icons,
    },
    { headers: { "Content-Type": "application/manifest+json" } },
  );
}
