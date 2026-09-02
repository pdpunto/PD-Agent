import { expect, test } from "@playwright/test";

test("early productive failure is terminal and exposes safe evidence", async ({ page }) => {
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
  await expect(page).toHaveURL(/\/executions\/[0-9a-f-]+(?:\?.*)?$/i);
  await expect(page.getByText("No he podido terminar este mod")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText(/Detenido/)).toBeVisible();
  await expect(page.getByText(/Trabajando/)).toHaveCount(0);

  await page.getByRole("button", { name: "Ver detalles" }).click();
  const human = page.getByRole("dialog");
  await expect(human).toContainText("FAILED");
  await expect(human).not.toContainText(/traceback|secret|C:\\\\Users/i);
  await human.getByRole("button", { name: "Close", exact: true }).click();

  await page.getByRole("button", { name: /Informaci.*cnica/ }).click();
  const technical = page.getByRole("dialog");
  await expect(technical).toContainText("FAILED");
  await expect(technical).not.toContainText(/traceback|secret|C:\\\\Users/i);

  expect(apiRequests).toContain("/api/v1/projects");
  expect(apiRequests.some((path) => /openai|gemini/i.test(path))).toBe(false);
});
