import AsyncStorage from "@react-native-async-storage/async-storage";

import { hasUnread, markNoticesSeen } from "@/lib/noticesSeen";

const MONDAY = "2026-10-19T04:00:00Z";
const TUESDAY = "2026-10-20T04:00:00Z";

test("no dot until the phone's copy is read, or with no notices", () => {
  expect(hasUnread(TUESDAY, undefined)).toBe(false);
  expect(hasUnread(undefined, null)).toBe(false);
});

test("a dot for a notice newer than the last one opened", () => {
  expect(hasUnread(MONDAY, null)).toBe(true);
  expect(hasUnread(TUESDAY, MONDAY)).toBe(true);
  expect(hasUnread(MONDAY, MONDAY)).toBe(false);
});

test("opening Notices is remembered per gym, never going back", async () => {
  markNoticesSeen("fitness-zone", TUESDAY);
  markNoticesSeen("fitness-zone", MONDAY);
  markNoticesSeen("iron-house", MONDAY);
  await Promise.resolve();
  expect(await AsyncStorage.getItem("gymbhai.noticesSeen.fitness-zone")).toBe(TUESDAY);
  expect(await AsyncStorage.getItem("gymbhai.noticesSeen.iron-house")).toBe(MONDAY);
});
