import type { Metadata } from "next";

import { MemberShell } from "@/components/memberApp/MemberShell";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ gym: string }>;
}): Promise<Metadata> {
  const { gym } = await params;
  return {
    manifest: `/${gym}/manifest.webmanifest`,
    appleWebApp: { capable: true, statusBarStyle: "default" },
    icons: { apple: "/apple-touch-icon.png" },
  };
}

export default async function MemberLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ gym: string }>;
}) {
  const { gym } = await params;
  return <MemberShell slug={gym}>{children}</MemberShell>;
}
