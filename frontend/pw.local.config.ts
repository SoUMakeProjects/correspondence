import base from "./playwright.config";
import { devices } from "@playwright/test";
export default {
  ...base,
  testDir: "/Users/soumakpaul/Downloads/correspondence/frontend/tests/e2e",
  outputDir: "/tmp/pw-results",
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
};
