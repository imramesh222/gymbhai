/** Where the app opens: choose a gym, sign in to it, or its Home. */
import { Redirect } from "expo-router";

import { useSession } from "@/lib/session";

export default function Start() {
  const { gym, signedIn } = useSession();
  if (!gym) return <Redirect href="/choose-gym" />;
  if (!signedIn) return <Redirect href="/sign-in" />;
  return <Redirect href="/home" />;
}
