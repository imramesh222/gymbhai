import { Fragment } from "react";

import { t, type MessageKey } from "@/i18n";

/**
 * A translated sentence with elements in it, such as links: "{terms}" in the
 * text is replaced by `parts.terms`. The words stay in the translation file,
 * so a Nepali sentence can put the links wherever its grammar needs them.
 */
export function Trans({
  k,
  parts,
}: {
  k: MessageKey;
  parts: Record<string, React.ReactNode>;
}) {
  return (
    <>
      {t(k)
        .split(/(\{\w+\})/)
        .map((piece, index) => {
          const name = /^\{(\w+)\}$/.exec(piece)?.[1];
          return (
            <Fragment key={index}>
              {name && name in parts ? parts[name] : piece}
            </Fragment>
          );
        })}
    </>
  );
}
