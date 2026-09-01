import { expect, test } from "@playwright/test";

test.describe("Point 11 deterministic UX acceptance", () => {
  test("projects Home intent and terminal execution states without creating work", async ({ page }) => {
    await page.route("**/api/v1/projects", async (route) => {
      if (route.request().method() === "GET") {
        await route.fulfill({ json: [] });
        return;
      }
      await route.continue();
    });
    await page.route("**/api/v1/executions/00000000-0000-4000-8000-000000000001", async (route) => {
      await route.fulfill({
        json: {
          execution_id: "00000000-0000-4000-8000-000000000001",
          run_id: "00000000-0000-4000-8000-000000000002",
          task_id: "00000000-0000-4000-8000-000000000003",
          status: "BLOCKED",
          reason: "validation blocked",
          terminal: true,
          current_milestone: null,
          current_activity: null,
          latest_sequence: 1,
        },
      });
    });
    await page.goto("/");
    await page.getByLabel("What should we build?").fill("Add a Server Core block");
    await page.getByRole("button", { name: /Start a task/ }).click();
    await expect(page).toHaveURL(/\/projects\?request=/);
    await page.goto("/executions/00000000-0000-4000-8000-000000000001");
    await expect(page.getByText("No he podido terminar este mod")).toBeVisible();
    await expect(page.getByText("Detenido · No se pudo completar")).toBeVisible();
    await expect(page.getByText(/Trabajando/)).toHaveCount(0);
    await expect(page.getByText("Entendiendo")).toHaveCount(0);
  });

  test("keeps evidence dialog keyboard accessible", async ({ page }) => {
    await page.route("**/api/v1/executions/evidence-test", async (route) => {
      await route.fulfill({
        json: {
          execution_id: "evidence-test",
          run_id: "run",
          task_id: "task",
          status: "SUCCEEDED",
          terminal: true,
          latest_sequence: 1,
        },
      });
    });
    await page.route("**/api/v1/executions/evidence-test/evidence/human", async (route) => {
      await route.fulfill({ json: { execution_id: "evidence-test", status: "SUCCEEDED", changes: ["src/main.java"], completion_summary: "PASS" } });
    });
    await page.goto("/executions/evidence-test");
    await page.getByRole("button", { name: "Ver detalles" }).click();
    await expect(page.getByRole("dialog")).toHaveAttribute("aria-modal", "true");
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
  });
});
