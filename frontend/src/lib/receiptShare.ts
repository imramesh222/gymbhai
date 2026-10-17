"use client";

/**
 * A receipt as a PDF, from a signed link anyone can open for 30 days
 * (PLAN.md §16.3, 8.4): download it, or hand it to the phone's share sheet
 * (WhatsApp, Viber, Messenger). Without a share sheet, the link is copied.
 */
export interface ReceiptLink {
  url: string;
  filename: string;
  text: string;
  expires_at: string;
}

export async function receiptFile(link: ReceiptLink): Promise<File> {
  const response = await fetch(link.url, { credentials: "omit" });
  if (!response.ok) throw new Error(`Receipt: ${response.status}`);
  return new File([await response.blob()], link.filename, { type: "application/pdf" });
}

export function download(file: File): void {
  const anchor = document.createElement("a");
  anchor.href = URL.createObjectURL(file);
  anchor.download = file.name;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(anchor.href), 10_000);
}

export type Shared = "shared" | "copied" | "cancelled";

/**
 * `file` is fetched beforehand where it can be: a share sheet needs the tap
 * that opened it to be recent, and a download in between can use that up.
 */
export async function share(link: ReceiptLink, file?: File): Promise<Shared> {
  try {
    if (file && navigator.canShare?.({ files: [file] })) {
      await navigator.share({ files: [file], title: link.filename, text: link.text });
      return "shared";
    }
    if (navigator.share) {
      await navigator.share({ title: link.filename, text: link.text, url: link.url });
      return "shared";
    }
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") return "cancelled";
    // Refused for another reason (no recent tap): copy the link instead.
  }
  await navigator.clipboard.writeText(`${link.text}\n${link.url}`);
  return "copied";
}
