// Metro, with ../shared (strings, QR, dates, money, API types; PLAN.md §17.1)
// bundled as if it were part of the app, under the same "@shared/..." name
// the web app uses.
const path = require("node:path");
const { getDefaultConfig } = require("expo/metro-config");

const shared = path.resolve(__dirname, "../shared/src");

/** @type {import('expo/metro-config').MetroConfig} */
const config = getDefaultConfig(__dirname);
config.watchFolders = [...(config.watchFolders ?? []), shared];
config.resolver.resolveRequest = (context, moduleName, platform) =>
  context.resolveRequest(
    context,
    moduleName.startsWith("@shared/")
      ? path.join(shared, moduleName.slice("@shared/".length))
      : moduleName,
    platform,
  );

module.exports = config;
