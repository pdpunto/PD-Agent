import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, ProductApiError } from "./client";

const jsonResponse = (body: unknown, status = 200) =>
  ({
    ok: status < 400,
    status,
    json: vi.fn().mockResolvedValue(body),
  }) as unknown as Response;
beforeEach(() => {
  vi.restoreAllMocks();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({})));
});

describe("typed product API client", () => {
  it("lists projects", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse([{ project_id: "p" }]));
    expect((await api.listProjects())[0].project_id).toBe("p");
  });
  it("gets a project", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ project_id: "p" }));
    expect((await api.getProject("p")).project_id).toBe("p");
  });
  it("creates a task with JSON", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ task_id: "t" }));
    await api.createTask("p", { request: "make" });
    expect(vi.mocked(fetch).mock.calls.at(-1)?.[1]).toMatchObject({
      method: "POST",
    });
  });
  it("starts an execution", async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ execution_id: "e" }));
    expect((await api.startExecution("t")).execution_id).toBe("e");
  });
  it("gets an execution snapshot", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ execution_id: "e" }));
    expect((await api.getExecution("e")).execution_id).toBe("e");
  });
  it("gets human and technical evidence", async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ execution_id: "e" }));
    expect((await api.getHumanEvidence("e")).execution_id).toBe("e");
    expect((await api.getTechnicalEvidence("e")).execution_id).toBe("e");
  });
  it("gets history and delivery metadata", async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({}));
    expect(await api.getHistory("p")).toEqual({});
    expect(await api.getDelivery("d")).toEqual({});
  });
  it("builds an artifact URL from the delivery identity", () => {
    expect(api.artifactUrl("d")).toBe("/api/v1/deliveries/d/artifact");
  });
  it("obtains a CSRF token for mutations", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse({ csrf_token: "csrf" }))
      .mockResolvedValueOnce(jsonResponse({ task_id: "t" }));
    await api.createTask("p", { request: "make" });
    const last = vi.mocked(fetch).mock.calls.at(-1);
    expect(last?.[1]).toMatchObject({ method: "POST" });
    expect(new Headers(last?.[1]?.headers).get("X-CSRF-Token")).toBe("csrf");
  });
  it("never puts CSRF in a query string", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ revealed: true }));
    await api.reveal("d");
    expect(vi.mocked(fetch).mock.calls.at(-1)?.[0]).not.toContain("csrf");
  });
  it("parses the canonical error envelope", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(
        {
          error: {
            code: "PROJECT_NOT_FOUND",
            message: "missing",
            request_id: "r",
          },
        },
        404,
      ),
    );
    await expect(api.getProject("missing")).rejects.toMatchObject({
      code: "PROJECT_NOT_FOUND",
      requestId: "r",
    });
  });
  it("uses a safe fallback for non-canonical errors", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({}, 500));
    await expect(api.getProject("p")).rejects.toThrow("local product service");
  });
  it("exposes the typed product error class", () => {
    expect(
      new ProductApiError({ code: "X", message: "safe", request_id: "r" }),
    ).toBeInstanceOf(Error);
  });
});
