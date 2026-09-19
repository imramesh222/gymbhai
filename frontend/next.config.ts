import type { NextConfig } from "next";

// Where the Next.js server reaches FastAPI. The browser never calls the API
// directly: it calls /api/* on this origin and Next.js forwards it. That keeps
// the refresh cookie first-party and removes CORS from the picture entirely.
//
// Rewrites are fixed when `next build` runs, so a production build needs
// API_INTERNAL_URL set at build time, not only at start.
const apiUrl = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // A self-contained server for the production image (Dockerfile.prod).
  output: "standalone",
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiUrl}/api/:path*` }];
  },
};

export default nextConfig;
