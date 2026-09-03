import { expect, test } from "@playwright/test";

test("unsupported task is rejected before productive execution", async ({ page }) => {
  const apiRequests: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/")) apiRequests.push(new URL(request.url()).pathname);
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Projects" }).click();
  await page.getByRole("button", { name: /New project/ }).click();

  const workspace = process.env.PD_AGENT_E2E_WORKSPACE;
  if (!workspace) throw new Error("Playwright workspace was not configured");
  await page.getByLabel("Name").fill("I12-E-R1 browser project");
  await page.getByLabel("Workspace").fill(workspace);
  await page.getByRole("button", { name: "Create project" }).click();
  await expect(page.getByRole("heading", { name: "I12-E-R1 browser project" })).toBeVisible();

  await page.getByLabel("Task request").fill("unsupported deterministic task");
  await page.getByRole("button", { name: "Start task" }).click();
  await expect(page).toHaveURL(/\/projects\/[0-9a-f-]+$/i);
  await expect(page.getByRole("alert")).toContainText("product operation could not be completed");

  expect(apiRequests).toContain("/api/v1/projects");
  expect(apiRequests.some((path) => /\/executions\//i.test(path))).toBe(false);
  expect(apiRequests.some((path) => /openai|gemini/i.test(path))).toBe(false);
});
