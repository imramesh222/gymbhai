import { Stack } from "expo-router";

/** Links into the app: opens the gym, then the screen (OpenGymLink). */
export default function GymLinkLayout() {
  return <Stack screenOptions={{ headerShown: false }} />;
}
