import { expect, test } from "@playwright/test";

test("real web stack supports project and task browser flow", async ({ page }) => {
  const requestedApiPaths: string[] = [];
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/")) requestedApiPaths.push(new URL(request.url()).pathname);
  });
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.goto("/");
  await expect(page).toHaveTitle("PD Agent");
  await expect(page.getByRole("heading", { name: /Turn an idea into/i })).toBeVisible();

  await page.getByRole("button", { name: "Projects" }).click();
  await expect(page).toHaveURL(/\/projects$/);
  await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
  const newProject = page.getByRole("button", { name: /New project/ });
  await newProject.focus();
  await expect(newProject).toBeFocused();
  await newProject.press("Enter");

  await page.getByLabel("Name").fill("Browser project");
  const workspace = process.env.PD_AGENT_E2E_WORKSPACE;
  if (!workspace) throw new Error("Playwright workspace was not configured");
  await page.getByLabel("Workspace").fill(workspace);
  await page.getByRole("button", { name: "Create project" }).click();
  await expect(page.getByRole("heading", { name: "Browser project" })).toBeVisible();
  const projectId = new URL(page.url()).pathname.split("/").pop();
  expect(projectId).toBeTruthy();

  const taskRequest = "Create a deterministic browser task";
  const taskResult = await page.evaluate(async ({ projectId, taskRequest }) => {
    const csrf = await fetch("/api/v1/security/csrf").then((response) => response.json());
    const response = await fetch(`/api/v1/projects/${projectId}/tasks`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        origin: window.location.origin,
        "x-csrf-token": csrf.csrf_token,
      },
      body: JSON.stringify({ request: taskRequest }),
    });
    return { status: response.status, body: await response.json() };
  }, { projectId, taskRequest });
  expect(taskResult.status).toBe(201);
  expect(taskResult.body.request).toBe(taskRequest);

  await page.reload();
  await expect(page.getByRole("heading", { name: "Browser project" })).toBeVisible();
  await expect(page.getByText(taskRequest)).toBeVisible();

  const invalidRoute = await page.evaluate(async () => {
    const response = await fetch("/api/v1/projects/not-a-uuid");
    return { status: response.status, body: await response.json() };
  });
  expect(invalidRoute.status).toBe(422);
  expect(invalidRoute.body.error.code).toBe("INVALID_REQUEST");
  expect(JSON.stringify(invalidRoute.body)).not.toMatch(/traceback|secret|C:\\\\/i);

  await page.goto("/projects");
  await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
  await page.reload();
  await expect(page.getByText("Browser project")).toBeVisible();
  expect(requestedApiPaths).toEqual(expect.arrayContaining([
    "/api/v1/projects",
    "/api/v1/projects/" + projectId,
    "/api/v1/projects/" + projectId + "/tasks",
  ]));
  expect(consoleErrors.filter((message) => !message.includes("status of 422"))).toEqual([]);
  expect(pageErrors).toEqual([]);
});
