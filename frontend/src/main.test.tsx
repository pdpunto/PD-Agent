import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import App from "./app/App";

describe("I9 product shell", () => {
  beforeEach(() => { window.history.replaceState({}, "", "/"); vi.restoreAllMocks(); vi.stubGlobal("fetch", vi.fn()); });
  it("renders Home with the primary hierarchy and no sidebar", () => { render(<App />); expect(screen.getByRole("heading", { name: /Turn an idea/i })).toBeInTheDocument(); expect(screen.queryByRole("complementary")).not.toBeInTheDocument(); expect(screen.getByLabelText("What should we build?")).toBeInTheDocument(); });
  it("navigates the canonical routes", () => { render(<App />); fireEvent.click(screen.getByRole("button", { name: "Projects" })); expect(screen.getByRole("heading", { name: "Projects" })).toBeInTheDocument(); fireEvent.click(screen.getByRole("button", { name: "Settings" })); expect(screen.getByRole("heading", { name: "Settings" })).toBeInTheDocument(); });
  it("keeps settings truthful and hides operational controls", () => { render(<App />); fireEvent.click(screen.getByRole("button", { name: "Settings" })); expect(screen.getByText(/No configurable settings/i)).toBeInTheDocument(); expect(screen.queryByText(/provider|model|api key|billing/i)).not.toBeInTheDocument(); });
  it("opens and closes accessible details, restoring focus", async () => { window.history.replaceState({}, "", "/executions/demo"); vi.mocked(fetch).mockResolvedValue({ ok: true, status: 200, json: async () => ({ execution_id: "demo", run_id: "demo", task_id: "task", status: "RUNNING", terminal: false, latest_sequence: 1 }) } as Response); render(<App />); const trigger = await screen.findByRole("button", { name: "Ver detalles" }); trigger.focus(); fireEvent.click(trigger); expect(screen.getByRole("dialog")).toHaveAttribute("aria-modal", "true"); fireEvent.keyDown(document, { key: "Escape" }); await waitFor(() => expect(trigger).toHaveFocus()); });
  it("keeps execution neutral without fake progress or delivery", () => { window.history.replaceState({}, "", "/executions/demo"); vi.mocked(fetch).mockReturnValue(new Promise(() => {})); render(<App />); expect(screen.getByText(/Loading the current status/i)).toBeInTheDocument(); expect(screen.queryByText(/%|credits|download/i)).not.toBeInTheDocument(); });
});
