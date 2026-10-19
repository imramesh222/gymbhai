/**
 * From the sign-in screen: the QR the desk shows signs the member in with no
 * SMS code (PLAN.md §18.4). Once signed in, the navigator moves on to Home.
 */
import { deskToken } from "@shared/deskLink";
import { t } from "@shared/i18n";

import { QrScanner } from "@/components/QrScanner";
import { parseGymLink } from "@/lib/gymLink";
import { useSession } from "@/lib/session";

export default function ScanDesk() {
  const { signInAtDesk } = useSession();
  return (
    <QrScanner
      title={t("app.signIn.scanDeskHelp")}
      onCode={async (data) => {
        const link = parseGymLink(data);
        const token = deskToken(data);
        if (!link || !token) return t("app.signIn.notDeskQr");
        await signInAtDesk(link.slug, token);
      }}
    />
  );
}
