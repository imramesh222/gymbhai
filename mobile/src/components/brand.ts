import { DEFAULT_BRAND } from "@/lib/config";
import { useMe } from "@/lib/hooks";
import { useSession } from "@/lib/session";

/** The open gym's colour: the app takes on its gym's look (PLAN.md §17). */
export function useBrand(): string {
  const { gym } = useSession();
  const me = useMe().data;
  return me?.gym.brand_color ?? gym?.brand_color ?? DEFAULT_BRAND;
}
