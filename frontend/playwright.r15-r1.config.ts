import { defineConfig, devices } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = fileURLToPath(new URL(".", import.meta.url));
const repoRoot = resolve(frontendRoot, "..");
const python = resolve(repoRoot, ".venv-l0fix", "Scripts", "python.exe");
const testRoot = resolve(tmpdir(), "pd-agent-r15-r1-20260831-f9e6c3");
mkdirSync(testRoot, { recursive: true });
const workspace = resolve(testRoot, "workspace");
process.env.PD_AGENT_E2E_WORKSPACE = workspace;

export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: "r15-r1.spec.ts",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: "list",
  use: { baseURL: "http://127.0.0.1:8765", ...devices["Desktop Chrome"], trace: "retain-on-failure" },
  webServer: {
    command: `"${python}" -m tests.support.r15_r1_server`,
    cwd: repoRoot,
    env: { ...process.env, PD_AGENT_R15_R1_PORT: "8765", PD_AGENT_R15_R1_ROOT: testRoot, PD_AGENT_E2E_WORKSPACE: workspace },
    url: "http://127.0.0.1:8765/api/v1/health",
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
