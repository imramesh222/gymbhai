import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AdminShell } from "./AdminShell";

const { pathname, permissions } = vi.hoisted(() => ({
  pathname: { current: "/admin" },
  permissions: { current: [] as string[] },
}));

vi.mock("next/navigation", () => ({
  usePathname: () => pathname.current,
  useRouter: () => ({ replace: vi.fn() }),
}));
vi.mock("@/lib/auth", () => ({
  needsTwoStepSetup: () => false,
  useAuth: () => ({
    loading: false,
    signOut: vi.fn(),
    me: { staff: { is_platform_admin: true } },
    can: (key: string) => permissions.current.includes(key),
  }),
}));

describe("what an admin sees in /admin", () => {
  beforeEach(() => {
    pathname.current = "/admin";
    permissions.current = ["admin.billing"];
  });

  it("lists only the pages they may open", () => {
    render(<AdminShell>gyms</AdminShell>);
    expect(screen.getByRole("link", { name: "Gyms" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Gym referrals" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Admins" })).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /plans and prices/ }),
    ).not.toBeInTheDocument();
  });

  it("refuses a page they may not open, even typed in", () => {
    pathname.current = "/admin/admins";
    render(<AdminShell>the admins</AdminShell>);
    expect(screen.getByRole("alert")).toHaveTextContent("Ask the super admin");
    expect(screen.queryByText("the admins")).not.toBeInTheDocument();
  });

  it("gives the super admin the Admins page", () => {
    permissions.current = ["admin.admins"];
    pathname.current = "/admin/admins";
    render(<AdminShell>the admins</AdminShell>);
    expect(screen.getByRole("link", { name: "Admins" })).toBeInTheDocument();
    expect(screen.getByText("the admins")).toBeInTheDocument();
  });
});
