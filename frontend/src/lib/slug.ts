/** A gym address from its name: "Fitness Zone Pvt. Ltd." -> "fitness-zone-pvt-ltd". */
export function slugify(name: string): string {
  return name
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 40)
    .replace(/-+$/, "");
}

/** Where a gym's member app lives. */
export function memberAppUrl(slug: string): string {
  return `app.gymbhai.com/${slug || "…"}`;
}
