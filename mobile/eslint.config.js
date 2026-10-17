// https://docs.expo.dev/guides/using-eslint/
const { defineConfig } = require("eslint/config");
const expoConfig = require("eslint-config-expo/flat");

module.exports = defineConfig([
  expoConfig,
  {
    ignores: ["dist/*", "android/*", "ios/*"],
  },
  {
    // One tap is one request (PLAN.md §17.4): a control that calls the API
    // goes through useAction, which locks on the first tap and sends an
    // Idempotency-Key. Calling memberApi straight from a handler is refused.
    files: ["src/**/*.tsx"],
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector:
            "JSXAttribute[name.name=/^on(Press|LongPress|SubmitEditing|ValueChange)$/] CallExpression[callee.object.name='memberApi']",
          message:
            "Call the API from a control through useAction (src/lib/useAction.ts): one tap is one request.",
        },
      ],
    },
  },
]);
