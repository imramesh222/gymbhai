/**
 * The WebSocket, open while the app is on screen and signed in (PLAN.md §17.3).
 * Events re-read the screens they affect; a (re)connect re-reads everything,
 * since events may have been missed while away.
 */
import { useEffect } from "react";
import { AppState } from "react-native";

import { freshAccessToken } from "./api";
import { SOCKET_URL } from "./config";
import { LiveSocket } from "./live";
import { onOnlineChange, isOnline } from "./online";
import { invalidateFor } from "./query";
import { useSession } from "./session";

export function LiveUpdates() {
  const { gym, signedIn } = useSession();
  const slug = gym?.slug;

  useEffect(() => {
    if (!slug || !signedIn) return;
    const socket = new LiveSocket({
      url: SOCKET_URL,
      // A token with at least two minutes left, so it outlives the handshake.
      getToken: (force) => freshAccessToken(force ? 600 : 120),
      onEvent: (type) => invalidateFor(slug, type),
      onReady: () => invalidateFor(slug, "everything"),
    });
    if (AppState.currentState === "active") socket.start();

    const appState = AppState.addEventListener("change", (state) => {
      // In the background the phone would cut it anyway; reconnect on return.
      if (state === "active") {
        socket.start();
        socket.nudge();
      } else if (state === "background") {
        socket.stop();
      }
    });
    const network = onOnlineChange(() => {
      if (isOnline()) socket.nudge();
    });
    return () => {
      appState.remove();
      network();
      socket.stop();
    };
  }, [slug, signedIn]);

  return null;
}
