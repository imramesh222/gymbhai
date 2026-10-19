import { deskToken } from "@shared/deskLink";

import { parseGymLink } from "@/lib/gymLink";
import { screenFor } from "@/lib/push";

jest.mock("expo-notifications", () => ({}));
jest.mock("expo-router", () => ({ router: {} }));
jest.mock("expo-constants", () => ({}));

test.each([
  ["https://app.gymbhai.com/fitness-zone?b=123", "fitness-zone", []],
  ["http://192.168.1.20:3000/fitness-zone", "fitness-zone", []],
  ["gymbhai://fitness-zone/join", "fitness-zone", ["join"]],
  ["app.gymbhai.com/Fitness-Zone", "fitness-zone", []],
  ["  fitness-zone ", "fitness-zone", []],
])("%s is %s", (input, slug, rest) => {
  expect(parseGymLink(input)).toEqual({ slug, rest });
});

test.each([
  "",
  "https://example.com/",
  "not a gym!",
  "WIFI:S:home;;",
  "gb1.abc.123.sig",
])("%s is not a gym", (input) => {
  expect(parseGymLink(input)).toBeNull();
});

test("the desk's sign-in QR names its gym and carries a one-time token", () => {
  const token = "Q2xlYW5fdG9rZW4tZm9yLXRlc3Rz";
  const url = `https://app.gymbhai.com/fitness-zone#desk=${token}`;
  expect(parseGymLink(url)).toEqual({ slug: "fitness-zone", rest: [] });
  expect(deskToken(url)).toBe(token);
  // The poster's QR has none: it only opens the gym.
  expect(deskToken("https://app.gymbhai.com/fitness-zone?b=123")).toBeNull();
});

test("a notification opens the screen it's about", () => {
  expect(screenFor("/fitness-zone/renew", "fitness-zone")).toBe("/renew");
  expect(screenFor("/fitness-zone", "fitness-zone")).toBe("/home");
  expect(screenFor("/fitness-zone/freeze", "fitness-zone")).toBe("/freeze");
  expect(screenFor("/fitness-zone/profile", "fitness-zone")).toBe("/me");
  expect(screenFor("/fitness-zone/unknown", "fitness-zone")).toBe("/home");
  // Another gym on this phone: through the link route, which opens it.
  expect(screenFor("/other-gym/renew", "fitness-zone")).toBe("/other-gym/renew");
  expect(screenFor("https://evil.example/x", "fitness-zone")).toBeNull();
  expect(screenFor(undefined, "fitness-zone")).toBeNull();
});
