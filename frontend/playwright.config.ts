import { defineConfig, devices } from "@playwright/test";
import { mkdirSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(frontendRoot, "..");
const isolatedRoot = mkdtempSync(resolve(tmpdir(), "pd-agent-i12-d-"));
const productDataRoot = resolve(isolatedRoot, "product-data");
const runsRoot = resolve(isolatedRoot, "runs");
const workspaceRoot = resolve(isolatedRoot, "workspace");
mkdirSync(workspaceRoot);
const pdAgent = resolve(repoRoot, ".venv-l0fix", "Scripts", "pd-agent.exe");
process.env.PD_AGENT_E2E_WORKSPACE = workspaceRoot;
process.env.PD_AGENT_I12_D_TEMP_ROOT = isolatedRoot;

export default defineConfig({
  testDir: "./tests/e2e",
  globalTeardown: "./playwright.global-teardown.ts",
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: [["list"], ["html", { outputFolder: resolve(isolatedRoot, "playwright-report"), open: "never" }]],
  use: {
    baseURL: "http://127.0.0.1",
    ...devices["Desktop Chrome"],
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: {
    command: `"${pdAgent}" web --host 127.0.0.1 --port 80 --provider openai --model gpt-5.6-luna --frontend-dist "${resolve(frontendRoot, "dist")}" --product-data-root "${productDataRoot}" --runs-dir "${runsRoot}"`,
    cwd: repoRoot,
    env: {
      ...process.env,
      OPENAI_API_KEY: "playwright-offline-no-dispatch",
      PD_AGENT_WEB_HOST: "127.0.0.1",
    },
    url: "http://127.0.0.1/api/v1/health",
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
