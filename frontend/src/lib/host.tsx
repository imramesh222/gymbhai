"use client";

import { createContext, useContext } from "react";

/**
 * This site's own address as people type it: "gymbhai.com.np", or
 * "localhost:3000" in development. It comes from the request
 * (app/layout.tsx), so the address is written nowhere in the code: the
 * pages show whichever address GymBhai is served from.
 */
const Context = createContext("");

export function HostProvider({
  host,
  children,
}: {
  host: string;
  children: React.ReactNode;
}) {
  return <Context.Provider value={host}>{children}</Context.Provider>;
}

export function useHost(): string {
  return useContext(Context);
}
