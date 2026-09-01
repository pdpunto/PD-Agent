import { FormEvent, useEffect, useRef, useState } from "react";
import type { RefObject } from "react";
import { api, ProductApiError } from "../api/client";
import type {
  Delivery,
  Execution,
  HumanEvidence,
  Project,
  ProjectHistory,
  TechnicalEvidence,
} from "../api/types";

type Route = {
  name: "home" | "projects" | "project" | "execution" | "settings";
  id?: string;
  projectId?: string;
};
type Load<T> = {
  status: "loading" | "ready" | "error";
  data?: T;
  error?: string;
};
const routeFor = (path: string): Route => {
  const p = path.split("/").filter(Boolean);
  if (p[0] === "projects" && p[1]) return { name: "project", id: p[1] };
  if (p[0] === "projects") return { name: "projects" };
  if (p[0] === "executions" && p[1]) {
    return {
      name: "execution",
      id: p[1],
      projectId: new URLSearchParams(window.location.search).get("project") ?? undefined,
    };
  }
  if (p[0] === "settings") return { name: "settings" };
  return { name: "home" };
};
const safeError = (error: unknown) =>
  error instanceof ProductApiError
    ? { message: error.message, code: error.code }
    : {
        message: "The local service could not complete that request.",
      code: "REQUEST_FAILED",
    };
const terminalStatuses = new Set([
  "SUCCEEDED",
  "FAILED",
  "BLOCKED",
  "LIMIT_REACHED",
  "INTERRUPTED",
]);
const statusLabel = (status: string | null) => {
  if (status === "SUCCEEDED") return "Completado · Mod verificado";
  if (status && terminalStatuses.has(status)) return "Detenido · No se pudo completar";
  return "Trabajando · Procesando la solicitud";
};

export default function App() {
  const [route, setRoute] = useState(() => routeFor(window.location.pathname));
  const mainRef = useRef<HTMLElement>(null);
  const [executionStatus, setExecutionStatus] = useState<string | null>(null);
  const navigate = (path: string) => {
    window.history.pushState({}, "", path);
    setRoute(routeFor(path));
  };
  useEffect(() => {
    const onPop = () => setRoute(routeFor(window.location.pathname));
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  useEffect(() => {
    mainRef.current?.focus();
  }, [route.name, route.id]);
  useEffect(() => {
    setExecutionStatus(null);
  }, [route.name, route.id]);
  return (
    <Shell
      route={route}
      navigate={navigate}
      mainRef={mainRef}
      executionStatus={executionStatus}
      setExecutionStatus={setExecutionStatus}
    />
  );
}
function Shell({
  route,
  navigate,
  mainRef,
  executionStatus,
  setExecutionStatus,
}: {
  route: Route;
  navigate: (path: string) => void;
  mainRef: RefObject<HTMLElement | null>;
  executionStatus: string | null;
  setExecutionStatus: (status: string | null) => void;
}) {
  const settingsTrigger = useRef<HTMLButtonElement>(null);
  return (
    <div className="app-shell">
      <header className="topbar">
        <button
          className="brand"
          onClick={() => navigate("/")}
          aria-label="Ir al inicio"
        >
          <span className="brand-mark" aria-hidden="true">
            PD
          </span>
          <span>
            <strong>PD Agent</strong>
            <small>Minecraft Fabric specialist</small>
          </span>
        </button>
        <nav aria-label="Navegación principal">
          <button
            className={
              route.name === "projects" || route.name === "project"
                ? "nav-link active"
                : "nav-link"
            }
            onClick={() => navigate("/projects")}
          >
            Projects
          </button>
          <button
            ref={settingsTrigger}
            className={
              route.name === "settings" ? "nav-link active" : "nav-link"
            }
            onClick={() => navigate("/settings")}
          >
            Settings
          </button>
        </nav>
      </header>
      <main ref={mainRef} className="content" tabIndex={-1}>
        {route.name === "home" && <HomePage navigate={navigate} />}
        {route.name === "projects" && <ProjectsPage navigate={navigate} />}
        {route.name === "project" && (
          <ProjectPage projectId={route.id!} navigate={navigate} />
        )}
        {route.name === "execution" && (
          <ExecutionPage
            executionId={route.id!}
            projectId={route.projectId}
            navigate={navigate}
            onStatusChange={setExecutionStatus}
          />
        )}
        {route.name === "settings" && (
          <SettingsPage
            navigate={navigate}
            restoreFocus={() => settingsTrigger.current?.focus()}
          />
        )}
      </main>
      <footer className="statusbar" aria-live="polite" aria-atomic="true">
        <span className="status-dot" aria-hidden="true" />{" "}
        {route.name !== "execution" ? "Listo" : statusLabel(executionStatus)}
      </footer>
    </div>
  );
}
function HomePage({ navigate }: { navigate: (path: string) => void }) {
  const [request, setRequest] = useState("");
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const query = request.trim()
      ? `?request=${encodeURIComponent(request)}`
      : "";
    navigate(`/projects${query}`);
  };
  return (
    <section className="home-page" aria-labelledby="home-title">
      <div className="voxel-mark" role="img" aria-label="Minecraft Fabric visual identity">
        <span /><span /><span /><span /><span /><span /><span /><span /><span />
      </div>
      <div className="eyebrow">FABRIC / BUILD WITH CONFIDENCE</div>
      <h1 id="home-title">
        Turn an idea into
        <br />
        <em>a living mod.</em>
      </h1>
      <p className="lede">
        Describe what you want to make. PD Agent understands the Fabric
        ecosystem and shapes the work into a persistent project.
      </p>
      <form className="composer-shell" onSubmit={submit}>
        <label htmlFor="home-request">What should we build?</label>
        <textarea
          id="home-request"
          placeholder="Describe a block, item, mechanic, or idea..."
          rows={3}
          value={request}
          onChange={(event) => setRequest(event.target.value)}
        />
        <div className="composer-actions">
          <button
            className="quiet-action"
            onClick={() => navigate("/projects")}
            type="button"
          >
            Choose a Project
          </button>
          <button className="primary-action" type="submit" disabled={!request.trim()}>
            Start a task <span aria-hidden="true">&#8594;</span>
          </button>
        </div>
      </form>
    </section>
  );
}
function ProjectsPage({ navigate }: { navigate: (path: string) => void }) {
  const [state, setState] = useState<Load<Project[]>>({ status: "loading" });
  const [form, setForm] = useState(false);
  const [name, setName] = useState("");
  const [workspace, setWorkspace] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const initialRequest = new URLSearchParams(window.location.search).get("request") ?? "";
  const [request, setRequest] = useState(initialRequest);
  const projectPath = (projectId: string) => {
    const query = request.trim()
      ? `?request=${encodeURIComponent(request)}`
      : "";
    return `/projects/${projectId}${query}`;
  };
  useEffect(() => {
    let live = true;
    api
      .listProjects()
      .then((data) => live && setState({ status: "ready", data }))
      .catch(
        (e) =>
          live && setState({ status: "error", error: safeError(e).message }),
      );
    return () => {
      live = false;
    };
  }, []);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const project = await api.createProject({ name, workspace });
      navigate(projectPath(project.project_id));
    } catch (e) {
      setError(safeError(e).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <section aria-labelledby="projects-title">
      <div className="page-heading">
        <div>
          <div className="eyebrow">YOUR WORKSPACE</div>
          <h1 id="projects-title">Projects</h1>
          <p>Persistent homes for the mods you are shaping.</p>
        </div>
        <button className="primary-action" onClick={() => setForm((v) => !v)}>
          New project <span aria-hidden="true">&#8594;</span>
        </button>
      </div>
      {form && (
        <form className="inline-form" onSubmit={submit} aria-busy={busy}>
          <label>
            Name
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              maxLength={200}
            />
          </label>
          <label>
            Workspace
            <input
              value={workspace}
              onChange={(e) => setWorkspace(e.target.value)}
              required
            />
          </label>
          {error && <p role="alert">{error}</p>}
          <button className="primary-action" disabled={busy} aria-disabled={busy}>
            {busy ? "Creating..." : "Create project"}
          </button>
        </form>
      )}
      {state.status === "loading" && (
        <div className="state-panel" role="status">
          Loading projects...
        </div>
      )}
      {state.status === "error" && (
        <div className="state-panel error-state">
          <strong>Projects are unavailable right now.</strong>
          <span>{state.error}</span>
        </div>
      )}
      {state.status === "ready" && state.data?.length === 0 && (
        <div className="state-panel">
          <strong>No projects yet.</strong>
          <span>Your first project will appear here.</span>
        </div>
      )}
      {state.status === "ready" && !!state.data?.length && (
        <ul className="project-list">
          {state.data.map((project) => (
            <li key={project.project_id}>
              <button
              className="project-card"
                onClick={() => navigate(projectPath(project.project_id))}
            >
              <span className="project-glyph" aria-hidden="true">
                ✦
              </span>
              <span>
                <strong>{project.name}</strong>
                <small>{project.task_ids.length} tasks</small>
              </span>
              <span className="card-arrow" aria-hidden="true">
                &#8594;
              </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
function ProjectPage({
  projectId,
  navigate,
}: {
  projectId: string;
  navigate: (path: string) => void;
}) {
  const [project, setProject] = useState<Load<Project>>({ status: "loading" });
  const [history, setHistory] = useState<Load<ProjectHistory>>({
    status: "loading",
  });
  const [request, setRequest] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const initialRequest = new URLSearchParams(window.location.search).get("request") ?? "";
  useEffect(() => {
    setRequest(initialRequest);
  }, [initialRequest]);
  useEffect(() => {
    let live = true;
    Promise.all([api.getProject(projectId), api.getHistory(projectId)])
      .then(
        ([p, h]) =>
          live &&
          (setProject({ status: "ready", data: p }),
          setHistory({ status: "ready", data: h })),
      )
      .catch(
        (e) =>
          live && setProject({ status: "error", error: safeError(e).message }),
      );
    return () => {
      live = false;
    };
  }, [projectId]);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const task = await api.createTask(projectId, { request });
      const execution = await api.startExecution(task.task_id);
      navigate(`/executions/${execution.execution_id}?project=${encodeURIComponent(projectId)}`);
    } catch (e) {
      setError(safeError(e).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <section aria-labelledby="project-title">
      <button className="back-link" onClick={() => navigate("/projects")}>
        &#8592; All projects
      </button>
      {project.status === "loading" && (
        <div role="status">Loading project...</div>
      )}
      {project.status === "error" && (
        <div className="state-panel error-state" role="alert">
          {project.error}
        </div>
      )}
      {project.status === "ready" && (
        <>
          <div className="page-heading">
            <div>
              <div className="eyebrow">PROJECT</div>
              <h1 id="project-title">{project.data?.name}</h1>
              <p>Persistent mod project.</p>
            </div>
          </div>
          <div className="detail-grid">
            <form className="placeholder-card" onSubmit={submit} aria-busy={busy}>
              <span className="card-label">TASK COMPOSER</span>
              <h2>What do you want to change?</h2>
              <textarea
                aria-label="Task request"
                value={request}
                onChange={(e) => setRequest(e.target.value)}
                placeholder="Describe the next task for this project..."
                rows={4}
                required
              />
              <button className="primary-action" disabled={busy} aria-disabled={busy}>
                {busy ? "Starting..." : "Start task"}
              </button>
              {error && <p role="alert">{error}</p>}
            </form>
            <div className="placeholder-card">
              <span className="card-label">HISTORY</span>
              <h2>Project history</h2>
              {history.status === "loading" && (
                <p role="status">Loading history...</p>
              )}
              {history.status === "error" && (
                <p role="alert">{history.error}</p>
              )}
              {(history.data?.tasks ?? []).map((task) => (
              <div className="history-item" key={task.task_id}>
                  <strong>{task.request}</strong>
                  <small>{task.execution_ids.length} executions</small>
                  {history.data?.executions
                    .filter((execution) => execution.task_id === task.task_id)
                    .map((execution) => (
                      <span className="history-meta" key={execution.execution_id}>
                        {statusLabel(execution.status)} · {new Date(task.created_at).toLocaleString()}
                      </span>
                    ))}
                  {history.data?.deliveries
                    .filter((delivery) => delivery.task_id === task.task_id)
                    .map((delivery) => (
                      <a className="history-delivery" key={delivery.delivery_id} href={api.artifactUrl(delivery.delivery_id)}>
                        Delivery / JAR · {delivery.artifact_sha256}
                      </a>
                    ))}
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </section>
  );
}
function ExecutionPage({
  executionId,
  projectId,
  navigate,
  onStatusChange,
}: {
  executionId: string;
  projectId?: string;
  navigate: (path: string) => void;
  onStatusChange: (status: string | null) => void;
}) {
  const [snapshot, setSnapshot] = useState<Load<Execution>>({
    status: "loading",
  });
  const latest = useRef(-1);
  const polling = useRef(false);
  const hasSnapshot = useRef(false);
  const timer = useRef<number | undefined>(undefined);
  const [details, setDetails] = useState<"human" | "technical" | null>(null);
  const [evidence, setEvidence] = useState<
    HumanEvidence | TechnicalEvidence | null
  >(null);
  useEffect(() => {
    let active = true;
    const poll = async () => {
      if (!active || polling.current) return;
      polling.current = true;
      try {
        const next = await api.getExecution(executionId);
        const sequence = next.latest_sequence ?? 0;
        if (sequence >= latest.current) {
          latest.current = sequence;
          hasSnapshot.current = true;
          setSnapshot({ status: "ready", data: next });
          onStatusChange(next.status);
        }
        if (!next.terminal && active)
          timer.current = window.setTimeout(poll, 1000);
      } catch (e) {
        if (active && !hasSnapshot.current)
          setSnapshot({ status: "error", error: safeError(e).message });
        else if (active) timer.current = window.setTimeout(poll, 1000);
      } finally {
        polling.current = false;
      }
    };
    void poll();
    return () => {
      active = false;
      if (timer.current !== undefined) window.clearTimeout(timer.current);
    };
  }, [executionId, onStatusChange]);
  useEffect(() => {
    if (!details) return;
    let active = true;
    const load =
      details === "human"
        ? api.getHumanEvidence(executionId)
        : api.getTechnicalEvidence(executionId);
    load
      .then((data) => active && setEvidence(data))
      .catch(() => active && setEvidence(null));
    return () => {
      active = false;
    };
  }, [details, executionId]);
  const item = snapshot.data;
  const terminalFailure = item && (item.terminal || terminalStatuses.has(item.status)) && item.status !== "SUCCEEDED";
  return (
    <section aria-labelledby="execution-title">
      <button
        className="back-link"
        onClick={() => navigate(projectId ? `/projects/${projectId}` : "/projects")}
      >
        &#8592; Open project
      </button>
      <div className="eyebrow">EXECUTION</div>
      <h1 id="execution-title">Execution</h1>
      {snapshot.status === "loading" && (
        <div className="execution-panel">
          <div className="neutral-state">
            <span className="ring" aria-hidden="true" />
            <strong>PD Agent is working on your mod</strong>
            <span>Loading the current status...</span>
          </div>
          <span className="mono-id">{executionId}</span>
        </div>
      )}
      {snapshot.status === "error" && (
        <div className="state-panel error-state" role="alert">
          <strong>We could not load this execution.</strong>
          <span>{snapshot.error}</span>
        </div>
      )}
      {snapshot.status === "ready" && item && (
        <>
          <div
            className={`execution-panel ${item.status === "REPAIRING" ? "repairing" : ""}`}
          >
            {item.status === "SUCCEEDED" ? (
              <SuccessState executionId={executionId} />
            ) : terminalFailure ? (
              <FailureState status={item.status} reason={item.reason} />
            ) : (
              <WorkingState snapshot={item} />
            )}
          </div>
          <div className="detail-actions">
            <button
              className="quiet-action"
              onClick={() => setDetails("human")}
            >
              Ver detalles
            </button>
            <button
              className="quiet-action"
              onClick={() => setDetails("technical")}
            >
              Información técnica
            </button>
          </div>
          {details && (
            <EvidenceDialog
              kind={details}
              evidence={evidence}
              onClose={() => setDetails(null)}
            />
          )}
        </>
      )}
    </section>
  );
}
function WorkingState({ snapshot }: { snapshot: Execution }) {
  return (
    <div className="neutral-state">
      <span className="ring" aria-hidden="true" />
      <strong>PD Agent está trabajando en tu mod</strong>
      <span>{snapshot.current_activity || "Procesando la solicitud"}</span>
      <span className="milestone" role="status" aria-live="polite" aria-atomic="true">
        {snapshot.current_milestone || "Trabajando"}
      </span>
    </div>
  );
}
function SuccessState({ executionId }: { executionId: string }) {
  const [delivery, setDelivery] = useState<Delivery>();
  const [revealing, setRevealing] = useState(false);
  const [message, setMessage] = useState("");
  useEffect(() => {
    let active = true;
    api.findDelivery(executionId).then((found) => active && setDelivery(found)).catch(() => active && setDelivery(undefined));
    return () => { active = false; };
  }, [executionId]);
  const reveal = async () => {
    if (!delivery) return;
    setRevealing(true);
    setMessage("");
    try {
      const result = await api.reveal(delivery.delivery_id);
      setMessage(result.revealed ? "Carpeta abierta." : "La entrega está lista para abrir.");
    } catch (error) {
      setMessage(safeError(error).message);
    } finally {
      setRevealing(false);
    }
  };
  return (
    <div className="terminal-state success-state">
      <strong>¡Todo listo!</strong>
      <span>PD Agent ha creado y verificado tu mod.</span>
      {delivery && <div className="delivery-actions"><a className="primary-action" href={api.artifactUrl(delivery.delivery_id)}>Descargar JAR</a><button className="quiet-action" onClick={reveal} disabled={revealing}>{revealing ? "Abriendo..." : "Abrir carpeta"}</button>{message && <small role="status">{message}</small>}</div>}
      <small>La entrega aparecerá cuando el backend la confirme.</small>
    </div>
  );
}
function FailureState({
  status,
  reason,
}: {
  status: string;
  reason?: string | null;
}) {
  return (
    <div className="terminal-state failure-state">
      <strong>No he podido terminar este mod</strong>
      <span>
        {status === "BLOCKED"
          ? "La ejecución quedó bloqueada."
          : reason || "La ejecución terminó sin éxito."}
      </span>
    </div>
  );
}
function EvidenceDialog({
  kind,
  evidence,
  onClose,
}: {
  kind: "human" | "technical";
  evidence: HumanEvidence | TechnicalEvidence | null;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const restore = useRef<HTMLElement | null>(
    document.activeElement as HTMLElement,
  );
  useEffect(() => {
    const dialog = ref.current;
    const first = dialog?.querySelector<HTMLElement>("button");
    first?.focus();
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
        return;
      }
      if (e.key !== "Tab" || !dialog) return;
      const items = Array.from(dialog.querySelectorAll<HTMLElement>("button"));
      const firstItem = items[0];
      const lastItem = items[items.length - 1];
      if (e.shiftKey && document.activeElement === firstItem) {
        e.preventDefault();
        lastItem.focus();
      } else if (!e.shiftKey && document.activeElement === lastItem) {
        e.preventDefault();
        firstItem.focus();
      }
    };
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("keydown", key);
      restore.current?.focus();
    };
  }, [onClose]);
  const human = evidence as HumanEvidence | null;
  const technical = evidence as TechnicalEvidence | null;
  return (
    <div className="modal-backdrop" role="presentation">
      <div
        ref={ref}
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="evidence-title"
      >
        <button
          className="modal-close"
          onClick={onClose}
          aria-label="Close details"
        >
          &#215;
        </button>
        <div className="eyebrow">
          {kind === "human" ? "EVIDENCE" : "TECHNICAL"}
        </div>
        <h2 id="evidence-title">
          {kind === "human" ? "What happened" : "Technical information"}
        </h2>
        {evidence ? (
          <div className="evidence-copy">
            {kind === "human" ? (
              <>
                <p>{human?.status}</p>
                {human?.current_activity && <p>{human.current_activity}</p>}
                {human?.build_summary && <p>{human.build_summary}</p>}
                {human?.repair_summary && <p>{human.repair_summary}</p>}
                {human?.runtime_validation_summary && (
                  <p>{human.runtime_validation_summary}</p>
                )}
                {human?.completion_summary && <p>{human.completion_summary}</p>}
                {human?.artifact_summary && <p>{human.artifact_summary}</p>}
                {!!human?.changes?.length && (
                  <ul aria-label="Changes">
                    {human.changes.map((change) => <li key={change}>{change}</li>)}
                  </ul>
                )}
              </>
            ) : (
              <>
                <p>Status: {technical?.status}</p>
                {technical?.runtime_state && (
                  <p>Runtime: {technical.runtime_state}</p>
                )}
                {technical?.run_id && <p>Run ID: {technical.run_id}</p>}
                {technical?.execution_id && <p>Execution ID: {technical.execution_id}</p>}
                {technical?.started_at && <p>Started: {technical.started_at}</p>}
                {technical?.failure_classification && (
                  <p>Classification: {technical.failure_classification}</p>
                )}
                {technical?.artifact_sha256 && (
                  <p>Artifact: {technical.artifact_sha256}</p>
                )}
                {!!technical?.changed_files?.length && (
                  <p>Files: {technical.changed_files.join(", ")}</p>
                )}
                {!!technical?.build_attempts?.length && (
                  <p>Build attempts: {technical.build_attempts.length}</p>
                )}
                {!!technical?.validation_summaries?.length && (
                  <p>Validations: {technical.validation_summaries.map(validationSummary).join(" · ")}</p>
                )}
                {!!technical?.runtime_observations?.length && (
                  <p>Runtime observations: {technical.runtime_observations.length}</p>
                )}
                {!!technical?.evidence_refs?.length && (
                  <p>Evidence refs: {technical.evidence_refs.join(", ")}</p>
                )}
              </>
            )}
          </div>
        ) : (
          <p className="muted">Loading authoritative evidence...</p>
        )}
        <button className="primary-action" onClick={onClose}>
          Close
        </button>
      </div>
    </div>
  );
}
function validationSummary(value: Record<string, unknown>) {
  const stage = typeof value.stage === "string" ? value.stage : "validation";
  const status = typeof value.status === "string" ? value.status : "recorded";
  return `${stage}: ${status}`;
}

function SettingsPage({
  navigate,
  restoreFocus,
}: {
  navigate: (path: string) => void;
  restoreFocus: () => void;
}) {
  const dialogRef = useRef<HTMLElement>(null);
  const close = () => {
    navigate("/");
    window.setTimeout(restoreFocus, 0);
  };
  useEffect(() => {
    const dialog = dialogRef.current;
    const focusable = () =>
      Array.from(
        dialog?.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        ) ?? [],
      );
    const initialFocus = window.setTimeout(() => focusable()[0]?.focus(), 0);
    const key = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        close();
        return;
      }
      if (event.key !== "Tab" || !dialog) return;
      const items = focusable();
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (!dialog.contains(document.activeElement)) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus();
        return;
      }
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", key);
    return () => {
      window.clearTimeout(initialFocus);
      document.removeEventListener("keydown", key);
      restoreFocus();
    };
  }, [navigate, restoreFocus]);
  return (
    <section
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-labelledby="settings-title"
    >
      <button className="back-link" onClick={close}>
        &#8592; Close settings
      </button>
      <div className="eyebrow">PREVIEW</div>
      <h1 id="settings-title">Settings</h1>
      <div className="state-panel settings-panel">
        <strong>No configurable settings in this preview.</strong>
        <span>Operational configuration stays private.</span>
      </div>
    </section>
  );
}
