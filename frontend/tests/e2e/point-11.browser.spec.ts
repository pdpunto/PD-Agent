import { expect, test } from "@playwright/test";

const executionId = "00000000-0000-4000-8000-000000000001";
const projectId = "00000000-0000-4000-8000-000000000010";
const taskId = "00000000-0000-4000-8000-000000000020";

const execution = (status: string, milestone: string | null = null) => ({
  execution_id: executionId,
  run_id: "00000000-0000-4000-8000-000000000002",
  task_id: taskId,
  status,
  reason: status === "RUNNING" ? null : "validation result",
  terminal: status !== "RUNNING",
  current_milestone: milestone,
  current_activity: status === "RUNNING" ? "Procesando la solicitud" : null,
  latest_sequence: 1,
});

test.describe("Point 11 deterministic UX acceptance", () => {
  test("projects all backend execution states truthfully", async ({ page }) => {
    let current = execution("RUNNING");
    await page.route(`**/api/v1/executions/${executionId}*`, async (route) => {
      await route.fulfill({ json: current });
    });
    await page.goto(`/executions/${executionId}`);

    await expect(page.getByText("Trabajando · Procesando la solicitud")).toBeVisible();
    for (const status of ["SUCCEEDED", "FAILED", "BLOCKED", "LIMIT_REACHED", "INTERRUPTED"]) {
      current = execution(status);
      await page.reload();
      if (status === "SUCCEEDED") {
        await expect(page.getByText("Completado · Mod verificado")).toBeVisible();
      } else {
        await expect(page.getByText("Detenido · No se pudo completar")).toBeVisible();
      }
      await expect(page.getByText(/Trabajando/)).toHaveCount(0);
    }
  });

  test("does not invent a milestone and shows a real backend milestone", async ({ page }) => {
    let current = execution("RUNNING");
    await page.route(`**/api/v1/executions/${executionId}*`, async (route) => {
      await route.fulfill({ json: current });
    });
    await page.goto(`/executions/${executionId}`);
    await expect(page.getByText("Entendiendo")).toHaveCount(0);
    current = execution("RUNNING", "Compilando");
    await page.reload();
    await expect(page.getByText("Compilando")).toBeVisible();
  });

  test("preserves Home intent when selecting an existing Project", async ({ page }) => {
    const request = "Añade un bloque: Server Core / en_us";
    await page.route("**/api/v1/projects**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path.endsWith("/history")) {
        await route.fulfill({ json: { project_id: projectId, tasks: [], executions: [], deliveries: [] } });
      } else if (path.endsWith(`/projects/${projectId}`)) {
        await route.fulfill({ json: { project_id: projectId, name: "Project A", created_at: "2026-01-01", updated_at: "2026-01-01", task_ids: [] } });
      } else {
        await route.fulfill({ json: [{ project_id: projectId, name: "Project A", created_at: "2026-01-01", updated_at: "2026-01-01", task_ids: [] }] });
      }
    });
    await page.goto(`/projects?request=${encodeURIComponent(request)}`);
    await page.getByRole("button", { name: /Project A/ }).click();
    await expect(page.getByRole("textbox", { name: "Task request" })).toHaveValue(request);
  });

  test("preserves exact Home intent whitespace and reserved characters", async ({ page }) => {
    const request = "  A\u00f1ade un bloque: N\u00facleo / en_us?x=1&y=2  ";
    await page.route("**/api/v1/projects**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path.endsWith("/history")) {
        await route.fulfill({ json: { project_id: projectId, tasks: [], executions: [], deliveries: [] } });
      } else if (path.endsWith(`/projects/${projectId}`)) {
        await route.fulfill({ json: { project_id: projectId, name: "Project A", created_at: "2026-01-01", updated_at: "2026-01-01", task_ids: [] } });
      } else {
        await route.fulfill({ json: [{ project_id: projectId, name: "Project A", created_at: "2026-01-01", updated_at: "2026-01-01", task_ids: [] }] });
      }
    });
    await page.goto(`/projects?request=${encodeURIComponent(request)}`);
    await page.getByRole("button", { name: /Project A/ }).click();
    await expect(page.getByRole("textbox", { name: "Task request" })).toHaveValue(request);
  });

  test("does not create a Home intent from whitespace-only input", async ({ page }) => {
    await page.goto("/");
    const composer = page.getByLabel("What should we build?");
    await composer.fill("  \n\t  ");
    await expect(page.getByRole("button", { name: /Start a task/ })).toBeDisabled();
    await expect(page).toHaveURL(/\/$/);
  });

  test("returns Execution deterministically to its owner Project", async ({ page }) => {
    await page.route(`**/api/v1/executions/${executionId}*`, async (route) => {
      await route.fulfill({ json: execution("BLOCKED") });
    });
    await page.goto(`/executions/${executionId}?project=${projectId}`);
    await page.getByRole("button", { name: /Open project/ }).click();
    await expect(page).toHaveURL(new RegExp(`/projects/${projectId}$`));
  });

  test("shows History and allowlisted Technical Evidence", async ({ page }) => {
    await page.route(`**/api/v1/projects/${projectId}`, async (route) => {
      await route.fulfill({ json: { project_id: projectId, name: "Project A", created_at: "2026-01-01", updated_at: "2026-01-01", task_ids: [taskId] } });
    });
    await page.route(`**/api/v1/projects/${projectId}/history`, async (route) => {
      await route.fulfill({ json: {
        project_id: projectId,
        tasks: [{ task_id: taskId, project_id: projectId, request: "Server Core", created_at: "2026-01-01T10:00:00Z", execution_ids: [executionId] }],
        executions: [{ ...execution("SUCCEEDED"), created_at: "2026-01-01T10:00:00Z" }],
        deliveries: [{ delivery_id: "delivery", project_id: projectId, task_id: taskId, execution_id: executionId, artifact_sha256: "sha", created_at: "2026-01-01T10:00:00Z" }],
      } });
    });
    await page.route(`**/api/v1/executions/${executionId}*`, async (route) => {
      await route.fulfill({ json: execution("SUCCEEDED") });
    });
    await page.goto(`/projects/${projectId}`);
    await expect(page.getByText("Completado · Mod verificado")).toBeVisible();
    await expect(page.getByText(/Delivery \/ JAR/)).toBeVisible();
    await page.getByRole("button", { name: /Ver ejecuci/ }).click();
    await expect(page).toHaveURL(new RegExp(`/executions/${executionId}\\?project=${projectId}$`));

    await page.route(`**/api/v1/executions/${executionId}/evidence/technical`, async (route) => {
      await route.fulfill({ json: {
        execution_id: executionId,
        run_id: "run-2",
        status: "SUCCEEDED",
        started_at: "2026-01-01T10:00:00Z",
        changed_files: ["src/main.java"],
        build_attempts: [{ success: true }],
        validation_summaries: [{ stage: "BUILD", status: "PASS" }],
        runtime_observations: [],
        evidence_refs: ["evidence-1"],
      } });
    });
    await page.goto(`/executions/${executionId}`);
    await page.getByRole("button", { name: /Informaci.*cnica/ }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toContainText(executionId);
    await expect(dialog).toContainText("run-2");
    await expect(dialog).toContainText("2026-01-01T10:00:00Z");
    await expect(dialog).toContainText("BUILD: PASS");
    await expect(dialog).not.toContainText(/secret|authorization|traceback|prompt/i);
  });

  test("keeps Details and Settings keyboard accessible", async ({ page }) => {
    await page.route(`**/api/v1/executions/${executionId}*`, async (route) => {
      await route.fulfill({ json: execution("SUCCEEDED") });
    });
    await page.route(`**/api/v1/executions/${executionId}/evidence/human`, async (route) => {
      await route.fulfill({ json: { execution_id: executionId, status: "SUCCEEDED", changes: ["src/main.java"] } });
    });
    await page.goto(`/executions/${executionId}`);
    const details = page.getByRole("button", { name: "Ver detalles" });
    await details.focus();
    await details.press("Enter");
    const dialog = page.getByRole("dialog");
    await expect(dialog).toHaveAttribute("aria-modal", "true");
    await page.keyboard.press("Shift+Tab");
    await expect(dialog.getByRole("button", { name: "Close", exact: true })).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await expect(details).toBeFocused();

    const settings = page.getByRole("button", { name: "Settings" });
    await settings.focus();
    await settings.press("Enter");
    const settingsLayer = page.getByRole("dialog");
    await expect(settingsLayer).toHaveAttribute("aria-modal", "true");
    await expect(settingsLayer.getByRole("button", { name: /Close settings/ })).toBeFocused();
    await settingsLayer.getByRole("button", { name: /Close settings/ }).click();
    await expect(page).toHaveURL(/\/$/);
    await expect(settings).toBeFocused();

    await settings.press("Enter");
    const reopened = page.getByRole("dialog", { name: "Settings" });
    await expect(reopened).toBeVisible();
    await page.keyboard.press("Tab");
    await expect(reopened.getByRole("button", { name: /Close settings/ })).toBeFocused();
    await page.keyboard.press("Shift+Tab");
    await expect(reopened.getByRole("button", { name: /Close settings/ })).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(reopened).toHaveCount(0);
    await expect(settings).toBeFocused();
  });
});
