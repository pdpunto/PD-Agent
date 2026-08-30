import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { api } from "../api/client";
import "@testing-library/jest-dom/vitest";

beforeEach(() => {
  window.history.replaceState({}, "", "/");
  vi.restoreAllMocks();
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => [] }),
  );
});
const go = (label: string) =>
  fireEvent.click(screen.getByRole("button", { name: label }));
const running = {
  execution_id: "e",
  run_id: "e",
  task_id: "t",
  status: "RUNNING",
  terminal: false,
  latest_sequence: 1,
};
const project = {
  project_id: "project-1",
  name: "Demo",
  created_at: "2026-01-01",
  updated_at: "2026-01-01",
  task_ids: [],
};
const history = {
  project_id: "project-1",
  tasks: [],
  executions: [],
  deliveries: [],
};
describe("frontend route and state foundations", () => {
  it("renders the product identity", () => {
    render(<App />);
    expect(screen.getByText("Minecraft Fabric specialist")).toBeInTheDocument();
  });
  it("shows the minimal ready status", () => {
    render(<App />);
    expect(screen.getByText("Listo")).toBeInTheDocument();
  });
  it("shows the project loading state", () => {
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => {})));
    render(<App />);
    go("Projects");
    expect(screen.getByRole("status")).toHaveTextContent("Loading projects");
  });
  it("shows the project empty state", async () => {
    render(<App />);
    go("Projects");
    await waitFor(() =>
      expect(screen.getByText("No projects yet.")).toBeInTheDocument(),
    );
  });
  it("shows the project error state", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    render(<App />);
    go("Projects");
    await waitFor(() =>
      expect(screen.getByText(/unavailable/i)).toBeInTheDocument(),
    );
  });
  it("renders a project route shell", async () => {
    window.history.replaceState({}, "", "/projects/project-1");
    vi.mocked(fetch)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => project,
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => history,
      } as Response);
    render(<App />);
    expect(
      await screen.findByRole("heading", { name: "Demo" }),
    ).toBeInTheDocument();
    expect(screen.getByText("TASK COMPOSER")).toBeInTheDocument();
  });
  it("keeps project and task concepts distinct", async () => {
    window.history.replaceState({}, "", "/projects/project-1");
    vi.mocked(fetch)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => project,
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => history,
      } as Response);
    render(<App />);
    expect(await screen.findByText("PROJECT")).toBeInTheDocument();
    expect(screen.getByText("TASK COMPOSER")).toBeInTheDocument();
  });
  it("renders an execution route", () => {
    window.history.replaceState({}, "", "/executions/execution-1");
    render(<App />);
    expect(
      screen.getByRole("heading", { name: "Execution" }),
    ).toBeInTheDocument();
  });
  it("renders a neutral execution state", () => {
    window.history.replaceState({}, "", "/executions/execution-1");
    vi.mocked(fetch).mockReturnValue(new Promise(() => {}));
    render(<App />);
    expect(screen.getByText(/Loading the current status/i)).toBeInTheDocument();
  });
  it("supports human details", async () => {
    window.history.replaceState({}, "", "/executions/e");
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => running,
    } as Response);
    render(<App />);
    await screen.findByRole("button", { name: "Ver detalles" });
    go("Ver detalles");
    expect(screen.getByRole("dialog")).toHaveTextContent("What happened");
  });
  it("supports technical details", async () => {
    window.history.replaceState({}, "", "/executions/e");
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => running,
    } as Response);
    render(<App />);
    await screen.findByRole("button", { name: "Información técnica" });
    go("Información técnica");
    expect(screen.getByRole("dialog")).toHaveTextContent(
      "Technical information",
    );
  });
  it("closes details with Escape", async () => {
    window.history.replaceState({}, "", "/executions/e");
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => running,
    } as Response);
    render(<App />);
    await screen.findByRole("button", { name: "Ver detalles" });
    go("Ver detalles");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
  it("traps Tab at the dialog boundary", async () => {
    window.history.replaceState({}, "", "/executions/e");
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => running,
    } as Response);
    render(<App />);
    await screen.findByRole("button", { name: "Ver detalles" });
    go("Ver detalles");
    const close = screen.getByRole("button", { name: "Close details" });
    close.focus();
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(screen.getByRole("button", { name: "Close" })).toHaveFocus();
  });
  it("renders Settings without operational controls", () => {
    render(<App />);
    go("Settings");
    expect(
      screen.getByRole("heading", { name: "Settings" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/tokens|billing|endpoint/i),
    ).not.toBeInTheDocument();
  });
  it("renders unknown paths safely as Home", () => {
    window.history.replaceState({}, "", "/unknown");
    render(<App />);
    expect(
      screen.getByRole("heading", { name: /Turn an idea/i }),
    ).toBeInTheDocument();
  });
  it("renders a backend milestone", async () => {
    window.history.replaceState({}, "", "/executions/e");
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ...running, current_milestone: "Compilando" }),
    } as Response);
    render(<App />);
    expect(await screen.findByText("Compilando")).toBeInTheDocument();
  });
  it("renders backend activity", async () => {
    window.history.replaceState({}, "", "/executions/e");
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        ...running,
        current_activity: "Validando el artefacto",
      }),
    } as Response);
    render(<App />);
    expect(
      await screen.findByText("Validando el artefacto"),
    ).toBeInTheDocument();
  });
  it("renders Reparando only from the backend status", async () => {
    window.history.replaceState({}, "", "/executions/e");
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        ...running,
        status: "REPAIRING",
        current_milestone: "Reparando",
      }),
    } as Response);
    render(<App />);
    expect(await screen.findByText("Reparando")).toBeInTheDocument();
  });
  it("renders a truthful failed execution", async () => {
    window.history.replaceState({}, "", "/executions/e");
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        ...running,
        status: "FAILED",
        terminal: true,
        reason: "build_failed",
      }),
    } as Response);
    render(<App />);
    expect(
      await screen.findByText("No he podido terminar este mod"),
    ).toBeInTheDocument();
  });
  it("renders a blocked execution safely", async () => {
    window.history.replaceState({}, "", "/executions/e");
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ...running, status: "BLOCKED", terminal: true }),
    } as Response);
    render(<App />);
    expect(
      await screen.findByText("La ejecución quedó bloqueada."),
    ).toBeInTheDocument();
  });
  it("renders limit reached safely", async () => {
    window.history.replaceState({}, "", "/executions/e");
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        ...running,
        status: "LIMIT_REACHED",
        terminal: true,
        reason: "limit",
      }),
    } as Response);
    render(<App />);
    expect(await screen.findByText("limit")).toBeInTheDocument();
  });
  it("renders interrupted safely", async () => {
    window.history.replaceState({}, "", "/executions/e");
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        ...running,
        status: "INTERRUPTED",
        terminal: true,
        reason: "interrupted",
      }),
    } as Response);
    render(<App />);
    expect(await screen.findByText("interrupted")).toBeInTheDocument();
  });
  it("does not render percentages", async () => {
    window.history.replaceState({}, "", "/executions/e");
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => running,
    } as Response);
    render(<App />);
    await screen.findByText("Procesando la solicitud");
    expect(document.body.textContent).not.toMatch(/\d+%/);
  });
  it("does not render a Cancel control", () => {
    render(<App />);
    expect(
      screen.queryByRole("button", { name: /cancel/i }),
    ).not.toBeInTheDocument();
  });
  it("does not render human intervention controls", () => {
    render(<App />);
    expect(screen.queryByText(/necesito tu ayuda/i)).not.toBeInTheDocument();
  });
  it("does not render provider controls", () => {
    render(<App />);
    expect(
      screen.queryByText(/provider|model|api key/i),
    ).not.toBeInTheDocument();
  });
  it("does not render credits", () => {
    render(<App />);
    expect(screen.queryByText(/credits|billing/i)).not.toBeInTheDocument();
  });
  it("returns from a project to projects", async () => {
    window.history.replaceState({}, "", "/projects/project-1");
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => project,
    } as Response);
    render(<App />);
    await screen.findByText("PROJECT");
    fireEvent.click(screen.getByRole("button", { name: /All projects/i }));
    expect(
      screen.getByRole("heading", { name: "Projects" }),
    ).toBeInTheDocument();
  });
  it("keeps the execution identity in the URL-derived view", () => {
    window.history.replaceState({}, "", "/executions/execution-42");
    vi.mocked(fetch).mockReturnValue(new Promise(() => {}));
    render(<App />);
    expect(screen.getByText("execution-42")).toBeInTheDocument();
  });
  it("uses task request input in project context", async () => {
    window.history.replaceState({}, "", "/projects/project-1");
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => project,
    } as Response);
    render(<App />);
    expect(
      await screen.findByRole("textbox", { name: "Task request" }),
    ).toBeInTheDocument();
  });
  it("does not expose filesystem paths on Home", () => {
    render(<App />);
    expect(document.body.textContent).not.toMatch(/[A-Z]:\\/);
  });
  it("keeps success copy authoritative and delivery conditional", async () => {
    window.history.replaceState({}, "", "/executions/e");
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ...running, status: "SUCCEEDED", terminal: true }),
    } as Response);
    render(<App />);
    expect(await screen.findByText("¡Todo listo!")).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /Descargar JAR/i }),
    ).not.toBeInTheDocument();
  });
  it("exposes download and reveal actions only for a real delivery", async () => {
    window.history.replaceState({}, "", "/executions/e");
    vi.mocked(fetch).mockResolvedValue({ ok: true, status: 200, json: async () => ({ ...running, status: "SUCCEEDED", terminal: true }) } as Response);
    vi.spyOn(api, "findDelivery").mockResolvedValue({ delivery_id: "delivery-1", project_id: "p", task_id: "t", execution_id: "e", artifact_sha256: "sha", created_at: "2026-01-01" });
    const reveal = vi.spyOn(api, "reveal").mockResolvedValue({ delivery_id: "delivery-1", revealed: true, filename: "mod.jar" });
    render(<App />);
    expect(await screen.findByRole("link", { name: "Descargar JAR" })).toHaveAttribute("href", "/api/v1/deliveries/delivery-1/artifact");
    fireEvent.click(screen.getByRole("button", { name: "Abrir carpeta" }));
    await waitFor(() => expect(reveal).toHaveBeenCalledWith("delivery-1"));
    expect(await screen.findByRole("status")).toHaveTextContent("Carpeta abierta.");
  });
});
