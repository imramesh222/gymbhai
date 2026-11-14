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

/** Where a gym's member app lives, at this site's address (useHost()). */
export function memberAppUrl(host: string, slug: string): string {
  return `${host}/${slug || "…"}`;
}
