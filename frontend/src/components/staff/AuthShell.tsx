import { AuthSplit } from "@/components/AuthSplit";
import { LanguageSwitch } from "@/components/LanguageSwitch";
import { LegalLinks } from "@/components/legal/LegalLinks";

/** The frame around staff sign-in, forgot password and two-step sign-in. */
export function AuthShell({
  title,
  children,
  footer,
}: {
  title: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  return (
    <AuthSplit title={title}>
      <div className="mt-3">{children}</div>
      {footer && (
        <div className="mt-6 text-center text-sm text-slate-600">{footer}</div>
      )}
      <div className="mt-6 flex justify-center">
        <LanguageSwitch />
      </div>
      <LegalLinks />
    </AuthSplit>
  );
}
