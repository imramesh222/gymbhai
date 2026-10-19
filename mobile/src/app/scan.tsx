/**
 * Scan the QR on the gym's poster (PLAN.md §17.5), or the sign-in QR the desk
 * shows (§18.4), which also signs the member in, with no code.
 */
import { deskToken } from "@shared/deskLink";
import { t } from "@shared/i18n";

import { QrScanner } from "@/components/QrScanner";
import { parseGymLink } from "@/lib/gymLink";
import { memberApi } from "@/lib/memberApi";
import { useSession } from "@/lib/session";

export default function Scan() {
  const { openGym, signInAtDesk } = useSession();
  return (
    <QrScanner
      title={t("mobile.scan.title")}
      onCode={async (data) => {
        const link = parseGymLink(data);
        if (!link) return t("mobile.scan.notGym");
        const token = deskToken(data);
        if (token) await signInAtDesk(link.slug, token);
        else await openGym(await memberApi.gym(link.slug));
        // The gym is open: the navigator moves on to signing in, or Home.
      }}
    />
  );
}
