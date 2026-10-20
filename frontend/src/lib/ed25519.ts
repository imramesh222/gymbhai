// Ed25519 for the member QR's gb2 codes (PLAN.md §19.2), passed to the shared
// code in @shared/qr/memberQr, which has no packages of its own. Plain
// JavaScript, not WebCrypto: it works offline and on a plain-HTTP page.
import * as ed from "@noble/ed25519";
import { sha512 } from "@noble/hashes/sha2.js";

import type { Sign, Verify } from "@shared/qr/memberQr";

ed.hashes.sha512 = sha512;

export const sign: Sign = (message, secretKey) => ed.sign(message, secretKey);

export const verify: Verify = (signature, message, publicKey) =>
  ed.verify(signature, message, publicKey);
