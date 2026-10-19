import { describe, expect, it } from "vitest";

import { whatsappLink } from "./whatsapp";

describe("WhatsApp links", () => {
  it("adds Nepal's 977 to a stored number", () => {
    expect(whatsappLink("9812345678")).toBe("https://wa.me/9779812345678");
  });

  it("carries the message, Nepali and line breaks included", () => {
    const link = whatsappLink("9812345678", "नमस्ते Sita,\nRs 1,000 & more?");
    expect(link.startsWith("https://wa.me/9779812345678?text=")).toBe(true);
    expect(decodeURIComponent(link.split("?text=")[1])).toBe(
      "नमस्ते Sita,\nRs 1,000 & more?",
    );
  });
});
