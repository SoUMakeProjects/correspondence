import { defineConfig, devices } from "@playwright/test";
import { fileURLToPath } from "node:url";
import path from "node:path";

const workspace = fileURLToPath(new URL("..", import.meta.url));
const python = path.join(
  workspace,
  ".venv",
  process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
);
const testData = path.join(
  workspace,
  ".local",
  "browser-checks",
  Date.now().toString(),
);

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  use: { baseURL: "http://127.0.0.1:5174", trace: "retain-on-failure" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Edge"], channel: "msedge" } },
  ],
  webServer: [
    {
      command: `"${python}" -m uvicorn app.main:app --host 127.0.0.1 --port 8011`,
      cwd: workspace,
      env: {
        APP_DATA_DIR: testData,
        AZURE_OPENAI_BASE_URL: "",
        AZURE_OPENAI_API_KEY: "",
        AZURE_OPENAI_DEPLOYMENT: "",
        AZURE_OPENAI_LIVE_TESTS_ENABLED: "false",
      },
      url: "http://127.0.0.1:8011/api/health",
      reuseExistingServer: false,
    },
    {
      command: "npm run dev -- --port 5174",
      env: {
        APP_HOST: "127.0.0.1",
        APP_PORT: "8011",
        // Browser tests drive the Classic diagnostics workspace.
        VITE_ENABLE_DIAGNOSTICS: "true",
      },
      url: "http://127.0.0.1:5174",
      reuseExistingServer: false,
    },
    {
      command: "npm run dev:mailbox -- --port 5177",
      env: { APP_HOST: "127.0.0.1", APP_PORT: "8011" },
      url: "http://127.0.0.1:5177",
      reuseExistingServer: false,
    },
  ],
});
