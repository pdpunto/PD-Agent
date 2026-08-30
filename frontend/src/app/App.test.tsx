import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import "@testing-library/jest-dom/vitest";

beforeEach(() => { window.history.replaceState({}, "", "/"); vi.restoreAllMocks(); vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => [] })); });
const go = (label: string) => fireEvent.click(screen.getByRole("button", { name: label }));
describe("frontend route and state foundations", () => {
  it("renders the product identity", () => { render(<App />); expect(screen.getByText("Minecraft Fabric specialist")).toBeInTheDocument(); });
  it("shows the minimal ready status", () => { render(<App />); expect(screen.getByText("Listo")).toBeInTheDocument(); });
  it("shows the project loading state", () => { vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => {}))); render(<App />); go("Projects"); expect(screen.getByRole("status")).toHaveTextContent("Loading projects"); });
  it("shows the project empty state", async () => { render(<App />); go("Projects"); await waitFor(() => expect(screen.getByText("No projects yet.")).toBeInTheDocument()); });
  it("shows the project error state", async () => { vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline"))); render(<App />); go("Projects"); await waitFor(() => expect(screen.getByText(/unavailable/i)).toBeInTheDocument()); });
  it("renders a project route shell", () => { window.history.replaceState({}, "", "/projects/project-1"); render(<App />); expect(screen.getByRole("heading", { name: "Project detail" })).toBeInTheDocument(); expect(screen.getByText("TASK COMPOSER")).toBeInTheDocument(); });
  it("keeps project and task concepts distinct", () => { window.history.replaceState({}, "", "/projects/project-1"); render(<App />); expect(screen.getByText("PROJECT")).toBeInTheDocument(); expect(screen.getByText("TASK COMPOSER")).toBeInTheDocument(); });
  it("renders an execution route", () => { window.history.replaceState({}, "", "/executions/execution-1"); render(<App />); expect(screen.getByRole("heading", { name: "Execution" })).toBeInTheDocument(); });
  it("renders a neutral execution state", () => { window.history.replaceState({}, "", "/executions/execution-1"); render(<App />); expect(screen.getByText(/Authoritative status/i)).toBeInTheDocument(); });
  it("supports human details", () => { window.history.replaceState({}, "", "/executions/e"); render(<App />); go("Details"); expect(screen.getByRole("dialog")).toHaveTextContent("What PD Agent is doing"); });
  it("supports technical details", () => { window.history.replaceState({}, "", "/executions/e"); render(<App />); go("Technical details"); expect(screen.getByRole("dialog")).toHaveTextContent("Technical details"); });
  it("closes details with Escape", () => { window.history.replaceState({}, "", "/executions/e"); render(<App />); go("Details"); fireEvent.keyDown(document, { key: "Escape" }); expect(screen.queryByRole("dialog")).not.toBeInTheDocument(); });
  it("traps Tab at the dialog boundary", () => { window.history.replaceState({}, "", "/executions/e"); render(<App />); go("Details"); const close = screen.getByRole("button", { name: "Close details" }); close.focus(); fireEvent.keyDown(document, { key: "Tab", shiftKey: true }); expect(screen.getByRole("button", { name: "Close" })).toHaveFocus(); });
  it("renders Settings without operational controls", () => { render(<App />); go("Settings"); expect(screen.getByRole("heading", { name: "Settings" })).toBeInTheDocument(); expect(screen.queryByText(/tokens|billing|endpoint/i)).not.toBeInTheDocument(); });
  it("renders unknown paths safely as Home", () => { window.history.replaceState({}, "", "/unknown"); render(<App />); expect(screen.getByRole("heading", { name: /Turn an idea/i })).toBeInTheDocument(); });
});
