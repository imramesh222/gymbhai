import { isMessageKey, t } from "@shared/i18n";

import { ApiError, NetworkError } from "./api";

/** What to tell the member, in their language: the same rules as the web app. */
export function errorMessage(error: unknown): string {
  if (error instanceof NetworkError) return t("errors.network");
  if (error instanceof ApiError) {
    if (error.code === "validation_error" && error.fields.length > 0) {
      const names = error.fields.map(({ field }) => {
        const key = `field.${field}`;
        return isMessageKey(key) ? t(key) : field;
      });
      return t("errors.validation_error", { fields: [...new Set(names)].join(", ") });
    }
    if (error.code === "validation_error") return t("errors.validation_error_form");
    const key = `errors.${error.code}`;
    if (isMessageKey(key)) return t(key);
    return error.message || t("errors.generic");
  }
  return t("errors.generic");
}
