import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import App from "./app/App";

describe("I9 product shell", () => {
  beforeEach(() => { window.history.replaceState({}, "", "/"); vi.restoreAllMocks(); });
  it("renders Home with the primary hierarchy and no sidebar", () => { render(<App />); expect(screen.getByRole("heading", { name: /Turn an idea/i })).toBeInTheDocument(); expect(screen.queryByRole("complementary")).not.toBeInTheDocument(); expect(screen.getByLabelText("What should we build?")).toBeInTheDocument(); });
  it("navigates the canonical routes", () => { render(<App />); fireEvent.click(screen.getByRole("button", { name: "Projects" })); expect(screen.getByRole("heading", { name: "Projects" })).toBeInTheDocument(); fireEvent.click(screen.getByRole("button", { name: "Settings" })); expect(screen.getByRole("heading", { name: "Settings" })).toBeInTheDocument(); });
  it("keeps settings truthful and hides operational controls", () => { render(<App />); fireEvent.click(screen.getByRole("button", { name: "Settings" })); expect(screen.getByText(/No configurable settings/i)).toBeInTheDocument(); expect(screen.queryByText(/provider|model|api key|billing/i)).not.toBeInTheDocument(); });
  it("opens and closes accessible details, restoring focus", async () => { window.history.replaceState({}, "", "/executions/demo"); render(<App />); const trigger = screen.getByRole("button", { name: "Details" }); trigger.focus(); fireEvent.click(trigger); expect(screen.getByRole("dialog")).toHaveAttribute("aria-modal", "true"); fireEvent.keyDown(document, { key: "Escape" }); await waitFor(() => expect(trigger).toHaveFocus()); });
  it("keeps execution neutral without fake progress or delivery", () => { window.history.replaceState({}, "", "/executions/demo"); render(<App />); expect(screen.getByText(/Loading execution snapshot/i)).toBeInTheDocument(); expect(screen.queryByText(/%|credits|download/i)).not.toBeInTheDocument(); });
});
