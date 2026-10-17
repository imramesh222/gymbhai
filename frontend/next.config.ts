import path from "node:path";

import type { NextConfig } from "next";

// Where the Next.js server reaches FastAPI. The browser never calls the API
// directly: it calls /api/* on this origin and Next.js forwards it. That keeps
// the refresh cookie first-party and removes CORS from the picture entirely.
//
// Rewrites are fixed when `next build` runs, so a production build needs
// API_INTERNAL_URL set at build time, not only at start.
const apiUrl = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

// shared/ sits beside frontend/ (PLAN.md §17): one copy of the strings, QR,
// dates and types for the web and phone apps. The parent folder is the root
// so the bundler may read it; the Docker images keep the same layout.
const repoRoot = path.resolve(__dirname, "..");

const nextConfig: NextConfig = {
  turbopack: { root: repoRoot },
  outputFileTracingRoot: repoRoot,
  reactStrictMode: true,
  // A self-contained server for the production image (Dockerfile.prod).
  output: "standalone",
  // `next dev` otherwise writes AGENTS.md and CLAUDE.md here whenever an AI
  // agent runs it; the project's instructions live in the root CLAUDE.md.
  agentRules: false,
  // `next dev` serves its scripts to localhost only. Allow phones on the same
  // Wi-Fi (http://192.168.x.x:3000) for testing the member app and the door.
  // Development only: a production build ignores this.
  allowedDevOrigins: ["192.168.*.*", "10.*.*.*", "172.*.*.*"],
  async redirects() {
    // Expiring became Follow up (PLAN.md §16.3, 8.1): old bookmarks still work.
    return [
      { source: "/staff/expiring", destination: "/staff/follow-up", permanent: true },
      // Reminders moved to Messages → Automations (§16.3, 8.2).
      {
        source: "/staff/settings/reminders",
        destination: "/staff/automations",
        permanent: true,
      },
    ];
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiUrl}/api/:path*` }];
  },
};

export default nextConfig;
