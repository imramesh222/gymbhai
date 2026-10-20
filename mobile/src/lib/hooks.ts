/** The screens' data, cached on the phone and refreshed live (query.ts, live.ts). */
import { useQuery } from "@tanstack/react-query";

import { memberApi } from "./memberApi";
import { keys } from "./query";
import { useSession } from "./session";

function useGymKey() {
  const { gym, signedIn } = useSession();
  return { slug: gym?.slug ?? "", enabled: Boolean(gym && signedIn) };
}

export function useMe() {
  const { slug, enabled } = useGymKey();
  return useQuery({ queryKey: keys.me(slug), queryFn: memberApi.me, enabled });
}

export function usePayments() {
  const { slug, enabled } = useGymKey();
  return useQuery({
    queryKey: keys.payments(slug),
    queryFn: memberApi.payments,
    enabled,
  });
}

export function useRenewOptions() {
  const { slug, enabled } = useGymKey();
  return useQuery({
    queryKey: keys.renew(slug),
    queryFn: memberApi.renewOptions,
    enabled,
  });
}

export function useVisits(month: string) {
  const { slug, enabled } = useGymKey();
  return useQuery({
    queryKey: keys.visits(slug, month),
    queryFn: () => memberApi.visits(month),
    enabled,
  });
}

export function useNotices() {
  const { slug, enabled } = useGymKey();
  return useQuery({
    queryKey: keys.notices(slug),
    queryFn: memberApi.notices,
    enabled,
  });
}

export function useProgress() {
  const { slug, enabled } = useGymKey();
  return useQuery({
    queryKey: keys.progress(slug),
    queryFn: memberApi.progress,
    enabled,
  });
}

export function useClasses(from: string) {
  const { slug, enabled } = useGymKey();
  return useQuery({
    queryKey: keys.classes(slug, from),
    queryFn: () => memberApi.classes(from),
    enabled,
  });
}

export function useLatestFreeze() {
  const { slug, enabled } = useGymKey();
  return useQuery({
    queryKey: keys.freeze(slug),
    queryFn: memberApi.latestFreeze,
    enabled,
  });
}
