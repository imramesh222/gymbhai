/**
 * Which gym is open, and whether this phone is signed in to it (PLAN.md §17.5).
 *
 * The phone remembers the gyms it has opened (a member of two gyms switches
 * between them) and holds one refresh token per gym in secure storage. Being
 * signed in means holding that token: with no signal the app still opens, on
 * the saved membership and QR, and only the server can sign it out.
 */
import AsyncStorage from "@react-native-async-storage/async-storage";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import type { MemberSignIn, PublicGym } from "@shared/types";

import {
  forgetSession,
  hasSession,
  keepSession,
  refreshSession,
  refreshToken,
  setSessionHandlers,
  selectGym,
} from "./api";
import { memberApi } from "./memberApi";
import { forgetGymData, keys, queryClient } from "./query";

export type SavedGym = Pick<
  PublicGym,
  "slug" | "name" | "logo_url" | "brand_color" | "date_display" | "join_form"
>;

const GYMS_KEY = "gymbhai.gyms";
const CURRENT_KEY = "gymbhai.currentGym";

interface Session {
  /** Storage read: until then, show the splash. */
  ready: boolean;
  gyms: SavedGym[];
  gym: SavedGym | null;
  signedIn: boolean;
  /** Open this gym (adding it to the phone's list). */
  openGym: (gym: SavedGym) => Promise<void>;
  /** Back to "choose your gym", keeping the list. */
  closeGym: () => Promise<void>;
  signedInWith: (result: MemberSignIn) => Promise<void>;
  /** Called before signing out: turn this phone's notifications off. */
  setBeforeSignOut: (fn: (() => Promise<void>) | null) => void;
  signOut: () => Promise<void>;
}

const Context = createContext<Session | null>(null);

function saved(gym: SavedGym | PublicGym): SavedGym {
  const { slug, name, logo_url, brand_color, date_display, join_form } = gym;
  return { slug, name, logo_url, brand_color, date_display, join_form };
}

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [gyms, setGyms] = useState<SavedGym[]>([]);
  const [slug, setSlug] = useState<string | null>(null);
  const [signedIn, setSignedIn] = useState(false);
  const beforeSignOut = useRef<(() => Promise<void>) | null>(null);

  const rememberGym = useCallback(async (gym: SavedGym) => {
    let next: SavedGym[] = [];
    setGyms((list) => {
      next = [gym, ...list.filter((g) => g.slug !== gym.slug)];
      return next;
    });
    await AsyncStorage.setItem(GYMS_KEY, JSON.stringify(next));
  }, []);

  // The server's word on the session, and fresh gym details with it.
  useEffect(() => {
    setSessionHandlers({
      lost: (lostSlug) => {
        forgetGymData(lostSlug);
        if (lostSlug === slug) setSignedIn(false);
      },
      refreshed: (result) => {
        if (!result.me) return;
        queryClient.setQueryData(keys.me(result.me.gym.slug), result.me);
        void rememberGym(saved(result.me.gym));
      },
    });
    return () => setSessionHandlers({ lost: null, refreshed: null });
  }, [slug, rememberGym]);

  // On launch: the gyms this phone knows and the one that was open.
  useEffect(() => {
    void (async () => {
      let list: SavedGym[] = [];
      let current: string | null = null;
      try {
        list = JSON.parse((await AsyncStorage.getItem(GYMS_KEY)) ?? "[]");
        current = await AsyncStorage.getItem(CURRENT_KEY);
      } catch {
        // A damaged list: start again.
      }
      const open = list.find((g) => g.slug === current) ? current : null;
      selectGym(open);
      setGyms(list);
      setSlug(open);
      const held = open ? await hasSession(open) : false;
      setSignedIn(held);
      setReady(true);
      // Check with the server in the background; offline, carry on.
      if (held) refreshSession().catch(() => undefined);
    })();
  }, []);

  const openGym = useCallback(
    async (gym: SavedGym) => {
      await rememberGym(saved(gym));
      await AsyncStorage.setItem(CURRENT_KEY, gym.slug);
      selectGym(gym.slug);
      const held = await hasSession(gym.slug);
      setSlug(gym.slug);
      setSignedIn(held);
      if (held) refreshSession().catch(() => undefined);
    },
    [rememberGym],
  );

  const closeGym = useCallback(async () => {
    await AsyncStorage.removeItem(CURRENT_KEY);
    selectGym(null);
    setSlug(null);
    setSignedIn(false);
  }, []);

  const signedInWith = useCallback(
    async (result: MemberSignIn) => {
      if (!slug || !result.me) return;
      await keepSession(slug, result);
      queryClient.setQueryData(keys.me(slug), result.me);
      await rememberGym(saved(result.me.gym));
      setSignedIn(true);
    },
    [slug, rememberGym],
  );

  const signOut = useCallback(async () => {
    if (!slug) return;
    // A shared phone: the next member must not get this one's reminders.
    await beforeSignOut.current?.().catch(() => undefined);
    const token = await refreshToken(slug);
    // Offline, the server's session simply runs out; the phone forgets it now.
    if (token) await memberApi.logout(token).catch(() => undefined);
    await forgetSession(slug);
    forgetGymData(slug);
    setSignedIn(false);
  }, [slug]);

  const value = useMemo<Session>(
    () => ({
      ready,
      gyms,
      gym: gyms.find((g) => g.slug === slug) ?? null,
      signedIn,
      openGym,
      closeGym,
      signedInWith,
      setBeforeSignOut: (fn) => {
        beforeSignOut.current = fn;
      },
      signOut,
    }),
    [ready, gyms, slug, signedIn, openGym, closeGym, signedInWith, signOut],
  );

  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useSession(): Session {
  const context = useContext(Context);
  if (!context) throw new Error("useSession must be used inside SessionProvider");
  return context;
}

/** The open gym's address; only for screens behind a chosen gym. */
export function useSlug(): string {
  const { gym } = useSession();
  if (!gym) throw new Error("No gym is open");
  return gym.slug;
}
