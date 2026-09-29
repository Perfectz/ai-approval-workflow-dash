import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Clapperboard,
  LayoutGrid,
  ListChecks,
  Images,
  Activity,
  Workflow,
  Plus,
  ArrowUpRight,
  ChevronRight,
  ChevronLeft,
  Check,
  CheckCircle2,
  Copy,
  Download,
  FileText,
  Film,
  Headphones,
  Layers,
  LoaderCircle,
  MessageSquare,
  Play,
  RefreshCw,
  Settings2,
  Sparkles,
  X,
  ArrowUp,
  ArrowDown,
  Trash2,
  Terminal,
  Volume2,
  PanelRightOpen,
  AlertCircle,
  Search,
  Save,
  ExternalLink,
} from "lucide-react";
import "./styles.css";

type Json = Record<string, any>;
type MediaFile = {
  name: string;
  path: string;
  mime: string;
  size: number;
  sha256: string;
};
type Review = {
  id: string;
  decision: string;
  note: string;
  anchor: Json;
  created: string;
};
type Version = {
  id: string;
  number: number;
  artifact_id: string;
  content: string;
  prompt: string;
  metadata: Json;
  inputs: string[];
  files: MediaFile[];
  author: string;
  created: string;
  status: string;
  effective_status: string;
  stale: boolean;
  hash: string;
  reviews: Review[];
};
type Artifact = {
  id: string;
  title: string;
  kind: string;
  stage: string;
  scene_id: string | null;
  versions: Version[];
  latest: Version;
  approved_version_id: string | null;
};
type Scene = {
  id: string;
  title: string;
  ordinal: number;
  duration: number;
  revision: number;
  purpose: string;
  emotion: string;
  start_state: string;
  end_state: string;
  locked: string;
  flexible: string;
  voice_notes: string;
};
type Stage = {
  id: string;
  name: string;
  kind: string;
  scope: string;
  complete: boolean;
  instruction: string;
  deliverable: string;
  checks: string[];
};
type Project = {
  id: string;
  title: string;
  brief: string;
  revision: number;
  settings: Json;
  stage_status: Stage[];
  review_count: number;
  artifact_count: number;
  scene_count: number;
  scenes: Scene[];
  artifacts: Artifact[];
  events: Json[];
  tasks: Json[];
  jobs: Json[];
  timeline: Json[];
};
let token = "";
async function api<T = any>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const form = body instanceof FormData;
  const result = await fetch("/api" + path, {
    method,
    headers: {
      ...(method !== "GET" ? { "X-Director-Token": token } : {}),
      ...(!form && body ? { "Content-Type": "application/json" } : {}),
    },
    body: body ? (form ? body : JSON.stringify(body)) : undefined,
  });
  const value = await result.json();
  if (!result.ok)
    throw new Error(
      typeof value.detail === "string"
        ? value.detail
        : JSON.stringify(value.detail),
    );
  return value;
}
function downloadJson(value: unknown, name: string) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function mediaUrl(v: Version, index: number) {
  return `/api/media/${v.id}/${index}`;
}
const statusLabels: Json = {
  draft: "Draft",
  in_review: "Ready to review",
  approved: "Approved",
  changes_requested: "Changes requested",
  needs_update: "Inputs changed",
};
function Badge({ status }: { status: string }) {
  return (
    <span className={"badge " + status}>
      <span />
      {statusLabels[status] || status.replaceAll("_", " ")}
    </span>
  );
}
function Empty({
  icon: Icon = Layers,
  title,
  children,
}: {
  icon?: typeof Layers;
  title: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="empty">
      <span className="empty-icon">
        <Icon size={27} />
      </span>
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}
function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: React.ReactNode;
  hint?: string;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {hint && <small>{hint}</small>}
    </label>
  );
}
function Modal({
  title,
  subtitle,
  onClose,
  children,
  wide = false,
}: {
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: React.ReactNode;
  wide?: boolean;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    dialog.current?.showModal();
  }, []);
  return (
    <dialog
      ref={dialog}
      className={wide ? "modal wide" : "modal"}
      onCancel={onClose}
    >
      <div className="modal-head">
        <div>
          <h2>{title}</h2>
          {subtitle && <p>{subtitle}</p>}
        </div>
        <button
          aria-label="Close dialog"
          onClick={onClose}
          className="icon-button"
        >
          <X size={20} />
        </button>
      </div>
      {children}
    </dialog>
  );
}
function FormFooter({
  busy,
  onClose,
  label = "Save",
}: {
  busy: boolean;
  onClose: () => void;
  label?: string;
}) {
  return (
    <div className="form-footer">
      <button type="button" className="button secondary" onClick={onClose}>
        Cancel
      </button>
      <button className="button primary" disabled={busy}>
        {busy ? (
          <LoaderCircle size={16} className="spin" />
        ) : (
          <Check size={16} />
        )}{" "}
        {label}
      </button>
    </div>
  );
}

function App() {
  const [projects, setProjects] = useState<Project[]>([]),
    [project, setProject] = useState<Project | null>(null),
    [selected, setSelected] = useState(""),
    [versionId, setVersionId] = useState("");
  const [nav, setNav] = useState("Projects"),
    [stage, setStage] = useState("all"),
    [sceneId, setSceneId] = useState("all"),
    [tab, setTab] = useState("Review"),
    [search, setSearch] = useState("");
  const [modal, setModal] = useState(""),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [loading, setLoading] = useState(true),
    [doc, setDoc] = useState(""),
    [docName, setDocName] = useState("spec");
  const [next, setNext] = useState<Json | null>(null),
    [busy, setBusy] = useState(false);
  async function refresh(id = project?.id) {
    const list = await api<Project[]>("/projects");
    setProjects(list);
    if (id) setProject(await api<Project>("/projects/" + id));
  }
  async function openProject(id: string) {
    setLoading(true);
    try {
      const p = await api<Project>("/projects/" + id);
      setProject(p);
      setSelected("");
      setVersionId("");
      setSceneId("all");
      setStage("all");
      setTab("Review");
      setNav("Projects");
      localStorage.setItem("director-project", id);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }
  async function action(fn: () => Promise<unknown>, message?: string) {
    setBusy(true);
    setError("");
    try {
      await fn();
      await refresh();
      if (message) setNotice(message);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    (async () => {
      try {
        const session = await api("/session");
        token = session.token;
        const list = await api<Project[]>("/projects");
        setProjects(list);
        const saved = localStorage.getItem("director-project");
        await openProject(
          list.some((p) => p.id === saved)
            ? saved!
            : list.find((p) => p.settings.demo)?.id || list[0]?.id,
        );
      } catch (e) {
        setError(String(e));
        setLoading(false);
      }
    })();
  }, []);
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(""), 4500);
    return () => clearTimeout(timer);
  }, [notice]);
  useEffect(() => {
    if (!project) return;
    api(
      "/projects/" +
        project.id +
        "/next" +
        (sceneId !== "all" ? "?scene_id=" + sceneId : ""),
    )
      .then(setNext)
      .catch((e) => setError(e.message));
  }, [project, sceneId]);
  useEffect(() => {
    if (!project?.jobs.some((j) => ["queued", "running"].includes(j.status)))
      return;
    const timer = setInterval(
      () => refresh(project.id).catch((e) => setError(e.message)),
      2500,
    );
    return () => clearInterval(timer);
  }, [project?.id, project?.jobs.map((j) => j.status).join(",")]);
  useEffect(() => {
    if (nav === "Workflow & agents")
      api("/docs/" + docName)
        .then((d) => setDoc(d.content))
        .catch((e) => setError(e.message));
  }, [nav, docName]);
  const filtered = (project?.artifacts || []).filter(
    (a) =>
      (stage === "all" || a.stage === stage) &&
      (sceneId === "all" || a.scene_id === sceneId || !a.scene_id) &&
      a.title.toLowerCase().includes(search.toLowerCase()) &&
      (nav !== "Review queue" || a.latest.effective_status === "in_review"),
  );
  const artifact = filtered.find((a) => a.id === selected) || filtered[0];
  const version =
    artifact?.versions.find((v) => v.id === versionId) || artifact?.latest;
  const scene = project?.scenes.find(
    (s) => s.id === (artifact?.scene_id || sceneId),
  );
  const allReviews = projects.reduce((n, p) => n + p.review_count, 0);
  function selectArtifact(a: Artifact) {
    setSelected(a.id);
    setVersionId("");
    setTab("Review");
  }
  async function saved(result?: Json) {
    setModal("");
    await refresh();
    if (result?.artifact_id) {
      setSelected(result.artifact_id);
      setVersionId(result.version_id);
      setStage("all");
      setSceneId("all");
      setNav("Projects");
      setTab("Review");
    }
    setNotice("Saved to your project.");
  }
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            setNav("Projects");
          }}
        >
          <span>
            <Clapperboard size={22} />
          </span>
          <div>
            DIRECTOR<small>STUDIO</small>
          </div>
        </a>
        <div className="workspace-label">YOUR WORKSPACE</div>
        <nav>
          {[
            { name: "Projects", icon: LayoutGrid },
            { name: "Review queue", icon: ListChecks },
            { name: "Asset library", icon: Images },
            { name: "Activity", icon: Activity },
            { name: "Workflow & agents", icon: Workflow },
          ].map(({ name, icon: Icon }) => (
            <button
              className={nav === name ? "nav-item active" : "nav-item"}
              key={name}
              onClick={() => {
                setNav(name);
                setStage("all");
                setSceneId("all");
              }}
            >
              <Icon size={18} />
              {name}
              {name === "Review queue" && allReviews > 0 && <b>{allReviews}</b>}
            </button>
          ))}
        </nav>
        <div className="sidebar-note">
          <span className="green-dot" /> Local workspace
          <p>
            Your story.
            <br />
            Your final say.
          </p>
          <small>
            Versioned assets. Human approvals.
            <br />
            Connected agent workflow.
          </small>
        </div>
        <div className="sidebar-bottom">
          <div className="avatar">D</div>
          <div>
            Director workspace<small>Local · v0.1</small>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            Workspace <ChevronRight size={14} />
            <strong>{nav}</strong>
          </div>
          <div className="topbar-right">
            <span className="provider">
              <span className="green-dot" /> Local studio
            </span>
            <button
              className="icon-button"
              title="Refresh project"
              aria-label="Refresh project"
              onClick={() => action(() => refresh())}
            >
              <RefreshCw size={17} />
            </button>
            <div className="avatar small">D</div>
          </div>
        </header>
        <main>
          <div className="page-heading">
            <div>
              <div className="eyebrow">IDEA TO FINAL CUT</div>
              <h1>{nav === "Projects" ? "Your director’s desk" : nav}</h1>
              <p>
                {nav === "Projects"
                  ? "Keep the vision, the prompt, and every decision in one place."
                  : nav === "Review queue"
                    ? "Make the decisions that move your projects forward."
                    : nav === "Asset library"
                      ? "Every source, reference and take stays attached to its project."
                      : nav === "Activity"
                        ? "A durable record of work, handoffs and decisions."
                        : "A shared production process for you and your AI collaborators."}
              </p>
            </div>
            <button
              className="button primary"
              onClick={() => setModal("project")}
            >
              <Plus size={17} /> New project
            </button>
          </div>
          {error && (
            <div role="alert" className="alert error">
              <AlertCircle size={18} />
              <span>{error}</span>
              <button
                className="icon-button"
                aria-label="Dismiss error"
                onClick={() => setError("")}
              >
                <X size={16} />
              </button>
            </div>
          )}
          {loading && !project ? (
            <Empty icon={LoaderCircle} title="Opening your workspace…" />
          ) : (
            <>
              <section className="project-grid">
                {projects.map((p, i) => (
                  <button
                    key={p.id}
                    className={
                      "project-card " + (project?.id === p.id ? "selected" : "")
                    }
                    onClick={() => openProject(p.id)}
                  >
                    <div
                      className={
                        "project-mark mark-" + (p.settings.demo ? "lab" : i % 3)
                      }
                    >
                      {p.settings.demo ? (
                        <Headphones size={26} />
                      ) : (
                        <Clapperboard size={26} />
                      )}
                    </div>
                    <div className="project-copy">
                      <div className="project-card-title">
                        {p.title}
                        <ArrowUpRight size={16} />
                      </div>
                      <span>
                        {p.settings.demo
                          ? "TECHNICAL SANDBOX"
                          : `${p.settings.runtime_minutes} MIN TARGET · ${p.settings.aspect_ratio}`}
                      </span>
                      <div className="project-progress">
                        {p.stage_status.map((s) => (
                          <i key={s.id} className={s.complete ? "done" : ""} />
                        ))}
                      </div>
                      <small>
                        {p.review_count
                          ? `${p.review_count} awaiting your review`
                          : `${p.artifact_count} artifacts · ${p.scene_count} packages`}
                      </small>
                    </div>
                  </button>
                ))}
                <button
                  className="new-project-card"
                  onClick={() => setModal("project")}
                >
                  <Plus size={22} />
                  <span>A new story starts here</span>
                </button>
              </section>
              {project && (
                <>
                  <section className="project-header">
                    <div>
                      <div className="section-eyebrow">
                        CURRENT PROJECT{" "}
                        {project.settings.demo && (
                          <span className="sandbox-tag">SANDBOX</span>
                        )}
                      </div>
                      <h2>{project.title}</h2>
                    </div>
                    <div className="project-actions">
                      <button
                        className="button secondary"
                        onClick={() => setModal("direction")}
                      >
                        <Settings2 size={16} /> Direction
                      </button>
                      <a
                        className="button secondary"
                        href={"/api/projects/" + project.id + "/export"}
                      >
                        <Download size={16} /> Export project
                      </a>
                    </div>
                  </section>
                  {nav === "Workflow & agents" ? (
                    <section className="workflow-layout">
                      <div className="panel">
                        <div className="panel-heading">
                          <Workflow size={18} />
                          <h3>Production workflow</h3>
                          <span className="micro">v1</span>
                        </div>
                        <div className="workflow-list">
                          {project.stage_status.map((s, i) => (
                            <div className="workflow-step" key={s.id}>
                              <b>{String(i + 1).padStart(2, "0")}</b>
                              <div>
                                <h4>
                                  {s.name}{" "}
                                  <small>
                                    {s.scope === "scene"
                                      ? "per package"
                                      : "whole project"}
                                  </small>
                                </h4>
                                <p>{s.deliverable}</p>
                                <span>{s.checks.join(" · ")}</span>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                      <div>
                        <div className="panel agent-box">
                          <div className="panel-heading">
                            <Terminal size={18} />
                            <h3>Agent handoff</h3>
                          </div>
                          <div className="panel-body">
                            <div className="eyebrow">NEXT ACTION</div>
                            <h3>{next?.name}</h3>
                            <p>{next?.instruction}</p>
                            <Badge status={next?.state || "ready"} />
                            <p className="muted">
                              Agents claim work, pin approved inputs, register a
                              version, and submit it here. You approve the
                              result.
                            </p>
                            <button
                              className="button secondary"
                              onClick={() => {
                                downloadJson(next, "next-action.json");
                                setNotice("Handoff downloaded.");
                              }}
                            >
                              <Download size={15} /> Download handoff
                            </button>
                          </div>
                        </div>
                        <div className="panel docs-panel">
                          <div className="tabs small-tabs">
                            {[
                              ["spec", "Workflow spec"],
                              ["agents", "Agent tools"],
                              ["wan", "Wan & timing"],
                            ].map(([id, name]) => (
                              <button
                                key={id}
                                className={docName === id ? "active" : ""}
                                onClick={() => setDocName(id)}
                              >
                                {name}
                              </button>
                            ))}
                          </div>
                          <pre className="document-text">{doc}</pre>
                        </div>
                      </div>
                    </section>
                  ) : nav === "Activity" ? (
                    <section className="activity-layout">
                      <div className="panel">
                        <div className="panel-heading">
                          <Activity size={18} />
                          <h3>Project activity</h3>
                        </div>
                        {project.events.map((e) => (
                          <div className="event" key={e.id}>
                            <span className="event-dot" />
                            <div>
                              <strong>{e.message}</strong>
                              <small>
                                {e.actor} ·{" "}
                                {new Date(e.created).toLocaleString()}
                              </small>
                            </div>
                            <span className="micro">{e.kind}</span>
                          </div>
                        ))}
                      </div>
                      <div className="panel">
                        <div className="panel-heading">
                          <Terminal size={18} />
                          <h3>Jobs & agent tasks</h3>
                        </div>
                        <JobList project={project} />
                      </div>
                    </section>
                  ) : nav === "Asset library" ? (
                    <section className="library-grid">
                      {project.artifacts.flatMap((a) =>
                        a.versions.map((v) => (
                          <article key={v.id} className="panel asset-card">
                            <div className="asset-icon">
                              {v.files[0]?.mime.startsWith("image/") ? (
                                <img src={mediaUrl(v, 0)} alt={a.title} />
                              ) : a.kind === "audio" ? (
                                <Headphones size={34} />
                              ) : ["video", "previs", "edit"].includes(
                                  a.kind,
                                ) ? (
                                <Film size={34} />
                              ) : (
                                <FileText size={34} />
                              )}
                            </div>
                            <div className="panel-body">
                              <span className="micro">
                                {a.kind.toUpperCase()} · VERSION {v.number}
                              </span>
                              <h3>{a.title}</h3>
                              <Badge status={v.effective_status} />
                              <p className="muted">
                                {v.files.length} files · {v.inputs.length}{" "}
                                source versions
                              </p>
                              <button
                                className="button secondary"
                                onClick={() => {
                                  setNav("Projects");
                                  selectArtifact(a);
                                  setVersionId(v.id);
                                }}
                              >
                                Open package <ArrowUpRight size={15} />
                              </button>
                            </div>
                          </article>
                        )),
                      )}
                      {!project.artifacts.length && (
                        <Empty title="Your library starts with a premise">
                          Add your first artifact in the project view.
                        </Empty>
                      )}
                    </section>
                  ) : (
                    <>
                      <div className="stage-track">
                        {project.stage_status.map((s, i) => (
                          <button
                            key={s.id}
                            className={
                              (stage === s.id ? "active " : "") +
                              (s.complete ? "complete" : "")
                            }
                            onClick={() =>
                              setStage(stage === s.id ? "all" : s.id)
                            }
                          >
                            <span>
                              {s.complete ? <Check size={12} /> : i + 1}
                            </span>
                            {s.name}
                            {i < 7 && (
                              <ChevronRight className="stage-arrow" size={14} />
                            )}
                          </button>
                        ))}
                      </div>
                      <div className="view-bar">
                        <div className="tabs">
                          {["Review", "Film timeline", "Scene direction"].map(
                            (t) => (
                              <button
                                key={t}
                                className={tab === t ? "active" : ""}
                                onClick={() => setTab(t)}
                              >
                                {t === "Review" ? (
                                  <PanelRightOpen size={16} />
                                ) : t === "Film timeline" ? (
                                  <Film size={16} />
                                ) : (
                                  <Settings2 size={16} />
                                )}{" "}
                                {t}
                              </button>
                            ),
                          )}
                        </div>
                        <div className="view-tools">
                          <button
                            className="button text-button"
                            onClick={() => setModal("audio")}
                          >
                            <Volume2 size={16} /> Scratch audio
                          </button>
                          <button
                            className="button secondary"
                            onClick={() => setModal("artifact")}
                          >
                            <Plus size={16} /> Add artifact
                          </button>
                        </div>
                      </div>
                      {tab === "Film timeline" ? (
                        <Timeline
                          project={project}
                          refresh={refresh}
                          onError={setError}
                          notify={setNotice}
                        />
                      ) : tab === "Scene direction" ? (
                        <section className="scene-direction-grid">
                          {project.scenes.map((s) => (
                            <article
                              className="panel direction-card"
                              key={s.id}
                            >
                              <div className="panel-heading">
                                <span className="package-number">
                                  {String(s.ordinal).padStart(2, "0")}
                                </span>
                                <h3>{s.title}</h3>
                                <span className="micro">{s.duration}s</span>
                              </div>
                              <div className="panel-body">
                                <h4>Why this scene exists</h4>
                                <p>
                                  {s.purpose || "Add the dramatic purpose."}
                                </p>
                                <h4>Emotional turn</h4>
                                <p>{s.emotion || "Not set yet."}</p>
                                <div className="state-flow">
                                  <div>
                                    <small>START STATE</small>
                                    <p>{s.start_state || "Not set"}</p>
                                  </div>
                                  <ChevronRight size={18} />
                                  <div>
                                    <small>END STATE</small>
                                    <p>{s.end_state || "Not set"}</p>
                                  </div>
                                </div>
                                <h4>Locked direction</h4>
                                <p>{s.locked || "No locks recorded."}</p>
                                <button
                                  className="button secondary"
                                  onClick={() => {
                                    setSceneId(s.id);
                                    setModal("edit-scene");
                                  }}
                                >
                                  <Settings2 size={15} /> Edit direction
                                </button>
                              </div>
                            </article>
                          ))}
                          <button
                            className="new-scene-card"
                            onClick={() => setModal("scene")}
                          >
                            <Plus size={24} />
                            Add a scene package
                            <small>2–15 seconds · natural shot lengths</small>
                          </button>
                        </section>
                      ) : (
                        <section className="review-layout">
                          <aside className="artifact-rail panel">
                            <div className="rail-title">
                              <h3>Artifacts</h3>
                              <span>{filtered.length}</span>
                            </div>
                            <div className="search-field">
                              <Search size={14} />
                              <input
                                aria-label="Search artifacts"
                                placeholder="Find an artifact"
                                value={search}
                                onChange={(e) => setSearch(e.target.value)}
                              />
                            </div>
                            <select
                              className="compact-select"
                              aria-label="Filter by scene"
                              value={sceneId}
                              onChange={(e) => setSceneId(e.target.value)}
                            >
                              <option value="all">All scene packages</option>
                              {project.scenes.map((s) => (
                                <option key={s.id} value={s.id}>
                                  {s.ordinal}. {s.title}
                                </option>
                              ))}
                            </select>
                            <button
                              className={
                                "all-filter " +
                                (stage === "all" ? "active" : "")
                              }
                              onClick={() => setStage("all")}
                            >
                              All stages <span>{project.artifact_count}</span>
                            </button>
                            {filtered.map((a) => (
                              <button
                                key={a.id}
                                onClick={() => selectArtifact(a)}
                                className={
                                  "artifact-row " +
                                  (a.id === artifact?.id ? "active" : "")
                                }
                              >
                                <div className="artifact-thumb">
                                  {a.latest.files.find((f) =>
                                    f.mime.startsWith("image/"),
                                  ) ? (
                                    <img
                                      src={mediaUrl(
                                        a.latest,
                                        a.latest.files.findIndex((f) =>
                                          f.mime.startsWith("image/"),
                                        ),
                                      )}
                                      alt=""
                                    />
                                  ) : a.kind === "audio" ? (
                                    <Headphones size={22} />
                                  ) : ["video", "previs", "edit"].includes(
                                      a.kind,
                                    ) ? (
                                    <Film size={22} />
                                  ) : (
                                    <FileText size={22} />
                                  )}
                                </div>
                                <span className="artifact-row-copy">
                                  <strong>{a.title}</strong>
                                  <small>
                                    {a.kind} · v{a.latest.number}
                                  </small>
                                  <Badge status={a.latest.effective_status} />
                                </span>
                              </button>
                            ))}
                            {!filtered.length && (
                              <div className="rail-empty">
                                {nav === "Review queue"
                                  ? "No pending reviews in this project."
                                  : "No artifacts in this view."}
                              </div>
                            )}
                            <button
                              className="rail-add"
                              onClick={() => setModal("artifact")}
                            >
                              <Plus size={15} /> Add artifact
                            </button>
                          </aside>
                          <div className="editor-panel panel">
                            {artifact && version ? (
                              <>
                                <div className="editor-heading">
                                  <div>
                                    <span className="micro">
                                      {artifact.stage.toUpperCase()}{" "}
                                      {scene
                                        ? ` / PACKAGE ${String(scene.ordinal).padStart(2, "0")}`
                                        : " / PROJECT"}
                                    </span>
                                    <h3>{artifact.title}</h3>
                                  </div>
                                  <select
                                    aria-label="Artifact version"
                                    value={version.id}
                                    onChange={(e) =>
                                      setVersionId(e.target.value)
                                    }
                                  >
                                    {artifact.versions.map((v) => (
                                      <option key={v.id} value={v.id}>
                                        v{v.number} ·{" "}
                                        {statusLabels[v.effective_status]}
                                      </option>
                                    ))}
                                  </select>
                                </div>
                                <div className="canvas-prompt">
                                  <Preview
                                    artifact={artifact}
                                    version={version}
                                  />
                                  <PromptEditor
                                    project={project}
                                    artifact={artifact}
                                    version={version}
                                    onSaved={saved}
                                    onError={setError}
                                    notify={setNotice}
                                  />
                                </div>
                                <div className="package-footer">
                                  <span>
                                    <Layers size={14} /> {version.inputs.length}{" "}
                                    pinned inputs
                                  </span>
                                  <span>By {version.author}</span>
                                  <span>
                                    Saved{" "}
                                    {new Date(
                                      version.created,
                                    ).toLocaleDateString()}
                                  </span>
                                </div>
                              </>
                            ) : (
                              <div className="first-artifact">
                                <div className="empty-icon">
                                  <Sparkles size={30} />
                                </div>
                                <span className="eyebrow">
                                  {nav === "Review queue"
                                    ? "ALL CAUGHT UP"
                                    : "START WITH THE STORY"}
                                </span>
                                <h2>
                                  {nav === "Review queue"
                                    ? "Nothing waiting here."
                                    : "What happens, and why do we care?"}
                                </h2>
                                <p>
                                  {nav === "Review queue"
                                    ? "Switch projects to review more work, or return to the project to keep creating."
                                    : project.brief}
                                </p>
                                <div className="next-step">
                                  <small>NEXT STEP</small>
                                  <h3>{next?.name}</h3>
                                  <p>{next?.deliverable}</p>
                                </div>
                                <button
                                  className="button primary"
                                  onClick={() => setModal("artifact")}
                                >
                                  <Plus size={16} /> Add{" "}
                                  {next?.name?.toLowerCase() || "artifact"}
                                </button>
                              </div>
                            )}
                          </div>
                          <aside className="review-sidebar">
                            {artifact && version ? (
                              <ReviewPanel
                                project={project}
                                artifact={artifact}
                                version={version}
                                busy={busy}
                                act={action}
                              />
                            ) : (
                              <div className="panel">
                                <div className="panel-heading">
                                  <ListChecks size={18} />
                                  <h3>Your approval matters</h3>
                                </div>
                                <div className="panel-body">
                                  <p>
                                    Every stage has a review gate. Your agents
                                    can prepare work and request feedback; the
                                    next stage opens when you approve.
                                  </p>
                                  <ul className="quiet-list">
                                    <li>
                                      <CheckCircle2 size={15} /> Original
                                      versions are preserved
                                    </li>
                                    <li>
                                      <CheckCircle2 size={15} /> Changes flag
                                      affected work
                                    </li>
                                    <li>
                                      <CheckCircle2 size={15} /> Prompts stay
                                      with their outputs
                                    </li>
                                  </ul>
                                </div>
                              </div>
                            )}
                            <div className="connection-card">
                              <div>
                                <span className="provider-icon">W</span>
                                <strong>Wan 3.0</strong>
                                <span className="micro">PREPARE</span>
                              </div>
                              <p>Alibaba Cloud Model Studio</p>
                              <small>
                                Reference package export is available. Paid API
                                submission is not enabled.
                              </small>
                              <button
                                className="button text-button"
                                disabled={!sceneId || sceneId === "all"}
                                onClick={() =>
                                  action(async () => {
                                    downloadJson(
                                      await api(
                                        "/projects/" +
                                          project.id +
                                          "/generation/" +
                                          sceneId,
                                      ),
                                      "wan-generation-package.json",
                                    );
                                  }, "Generation package exported.")
                                }
                              >
                                <Download size={14} /> Export selected scene
                              </button>
                            </div>
                          </aside>
                        </section>
                      )}
                      <section className="scene-strip">
                        <div className="scene-strip-heading">
                          <div>
                            <span className="eyebrow">SCENE PACKAGES</span>
                            <h3>A film, one moment at a time.</h3>
                          </div>
                          <button
                            className="button secondary"
                            onClick={() => setModal("scene")}
                          >
                            <Plus size={15} /> Add package
                          </button>
                        </div>
                        <div className="scene-strip-items">
                          {project.scenes.map((s) => (
                            <button
                              key={s.id}
                              className={
                                "scene-chip " +
                                (sceneId === s.id ? "selected" : "")
                              }
                              onClick={() => {
                                setSceneId(sceneId === s.id ? "all" : s.id);
                                setSelected("");
                              }}
                            >
                              <b>{String(s.ordinal).padStart(2, "0")}</b>
                              <span>
                                <strong>{s.title}</strong>
                                <small>
                                  {s.duration}s ·{" "}
                                  {
                                    project.artifacts.filter(
                                      (a) => a.scene_id === s.id,
                                    ).length
                                  }{" "}
                                  artifacts
                                </small>
                              </span>
                              <ChevronRight size={15} />
                            </button>
                          ))}
                          {!project.scenes.length && (
                            <p className="muted">
                              Create packages after the screenplay takes shape.
                              Each can contain several shots.
                            </p>
                          )}
                        </div>
                      </section>
                      {project.jobs.some((j) =>
                        [
                          "queued",
                          "running",
                          "failed",
                          "needs_changes",
                        ].includes(j.status),
                      ) && (
                        <div className="panel jobs-bottom">
                          <JobList project={project} />
                        </div>
                      )}
                    </>
                  )}
                </>
              )}
            </>
          )}
          <footer className="page-footer">
            <span>DIRECTOR STUDIO</span>
            <span>Local files · Versioned decisions · Human direction</span>
            <button onClick={() => setNav("Workflow & agents")}>
              Workflow & agent guide <ArrowUpRight size={13} />
            </button>
          </footer>
        </main>
      </div>
      {notice && (
        <div className="toast" role="status">
          <CheckCircle2 size={18} />
          {notice}
        </div>
      )}
      {modal === "project" && (
        <ProjectForm
          onClose={() => setModal("")}
          onSaved={async (p) => {
            setModal("");
            await refresh(p.id);
            await openProject(p.id);
          }}
        />
      )}
      {project && modal === "artifact" && (
        <ArtifactForm
          project={project}
          stage={
            stage === "all"
              ? next?.stage === "complete"
                ? "edit"
                : next?.stage || "premise"
              : stage
          }
          sceneId={sceneId === "all" ? "" : sceneId}
          onClose={() => setModal("")}
          onSaved={saved}
        />
      )}
      {project && (modal === "scene" || modal === "edit-scene") && (
        <SceneForm
          project={project}
          scene={
            modal === "edit-scene"
              ? project.scenes.find((s) => s.id === sceneId)
              : undefined
          }
          onClose={() => setModal("")}
          onSaved={saved}
        />
      )}
      {project && modal === "direction" && (
        <DirectionForm
          project={project}
          onClose={() => setModal("")}
          onSaved={saved}
        />
      )}
      {project && modal === "audio" && (
        <AudioForm
          project={project}
          initialScene={sceneId === "all" ? project.scenes[0]?.id : sceneId}
          onClose={() => setModal("")}
          onSaved={saved}
        />
      )}
    </div>
  );
}

function Preview({
  artifact,
  version,
}: {
  artifact: Artifact;
  version: Version;
}) {
  const [fileIndex, setFileIndex] = useState(0),
    [compare, setCompare] = useState(false),
    [page, setPage] = useState(0);
  useEffect(() => {
    setFileIndex(
      Math.max(
        0,
        version.files.findIndex(
          (f) =>
            f.mime.startsWith("image/") ||
            f.mime.startsWith("video/") ||
            f.mime.startsWith("audio/"),
        ),
      ),
    );
    setPage(0);
    setCompare(false);
  }, [version.id]);
  const files = version.files,
    file = files[fileIndex],
    imageFiles = files
      .map((f, i) => ({ ...f, index: i }))
      .filter((f) => f.mime.startsWith("image/"));
  const old = artifact.versions.find((v) => v.number < version.number);
  const timing = version.metadata.timing;
  const imageFile = imageFiles[page];
  return (
    <div className="preview-column">
      <div className="subheading">
        <span>ARTIFACT PREVIEW</span>
        {old && (
          <button
            className={compare ? "mini-button active" : "mini-button"}
            onClick={() => setCompare(!compare)}
          >
            <Layers size={13} />
            {compare ? "Close compare" : "Compare"}
          </button>
        )}
      </div>
      {imageFile ? (
        <>
          <div
            className={
              "image-view " + (artifact.kind === "comic" ? "comic-view" : "")
            }
          >
            <img
              src={mediaUrl(version, imageFile.index)}
              alt={`${artifact.title} — image ${page + 1}`}
            />
            <a
              href={mediaUrl(version, imageFile.index)}
              target="_blank"
              rel="noreferrer"
              className="image-expand"
              aria-label="Open full-size image"
            >
              <ExternalLink size={15} />
            </a>
          </div>
          <div className="page-controls">
            <button
              className="icon-button"
              aria-label="Previous image"
              disabled={!page}
              onClick={() => setPage(page - 1)}
            >
              <ChevronLeft size={18} />
            </button>
            <span>
              {artifact.kind === "comic" ? "Page" : "Frame"} {page + 1} of{" "}
              {imageFiles.length}
            </span>
            <button
              className="icon-button"
              aria-label="Next image"
              disabled={page >= imageFiles.length - 1}
              onClick={() => setPage(page + 1)}
            >
              <ChevronRight size={18} />
            </button>
          </div>
        </>
      ) : file?.mime.startsWith("video/") ? (
        <video
          key={version.id + fileIndex}
          controls
          preload="metadata"
          src={mediaUrl(version, fileIndex)}
          className="video-preview"
        />
      ) : file?.mime.startsWith("audio/") ? (
        <div className="audio-preview">
          <div className="audio-art">
            <div className="orbit orbit-one" />
            <div className="orbit orbit-two" />
            <div className="audio-art-icon">
              <Headphones size={43} strokeWidth={1.3} />
            </div>
            <span>
              {version.metadata.timing
                ? "TEMPORARY VOICE & TIMING"
                : "AUDIO PREVIEW"}
            </span>
            <h3>
              {version.metadata.duration?.toFixed(1) || "—"}{" "}
              <small>SECONDS</small>
            </h3>
            <div className="audio-tags">
              {timing?.characters ? (
                Object.entries(timing.characters).map(
                  ([id, c]: [string, any]) => (
                    <span key={id}>
                      <i style={{ background: c.color }} />
                      {id}
                    </span>
                  ),
                )
              ) : (
                <span>IMPORTED AUDIO</span>
              )}
            </div>
          </div>
          {version.metadata.waveform && (
            <div className="waveform" aria-label="Measured audio waveform">
              {version.metadata.waveform.map((v: number, i: number) => (
                <i key={i} style={{ height: Math.max(3, v * 45) }} />
              ))}
            </div>
          )}
          <audio
            key={version.id + fileIndex}
            controls
            preload="metadata"
            src={mediaUrl(version, fileIndex)}
          />
          <span className="audio-caption">
            {file.name} ·{" "}
            {version.metadata.measured_by
              ? "measured duration"
              : "imported media"}
          </span>
        </div>
      ) : file?.mime === "application/pdf" ? (
        <iframe
          className="pdf-preview"
          title={artifact.title}
          src={mediaUrl(version, fileIndex)}
        />
      ) : (
        <div className="script-preview">
          <span className="paper-label">
            {artifact.kind.toUpperCase()} / V{version.number}
          </span>
          <h3>{artifact.title}</h3>
          <div className="prose-text">
            {version.content || "Open the attached files below."}
          </div>
        </div>
      )}
      {files.filter((f) => f.mime.startsWith("audio/")).length > 1 && (
        <select
          aria-label="Audio track"
          value={fileIndex}
          onChange={(e) => setFileIndex(+e.target.value)}
        >
          {files.map((f, i) =>
            f.mime.startsWith("audio/") ? (
              <option key={i} value={i}>
                {f.name}
              </option>
            ) : null,
          )}
        </select>
      )}
      {timing && (
        <div className="timing-cues">
          <div className="subheading">
            <span>DIALOGUE & SILENCE</span>
            <span>{timing.fps} FPS</span>
          </div>
          <div className="ruler">
            <span>0s</span>
            <span>{timing.target_duration / 2}s</span>
            <span>{timing.target_duration}s</span>
          </div>
          {Object.entries(timing.characters).map(
            ([id, char]: [string, any]) => (
              <div className="cue-row" key={id}>
                <label>
                  <i style={{ background: char.color }} />
                  {id}
                </label>
                <div className="cue-track">
                  {timing.lines
                    .filter((l: Json) => l.character === id)
                    .map((l: Json) => (
                      <div
                        key={l.id}
                        title={`${l.text} (${l.start}–${l.end}s)`}
                        style={{
                          left: `${(l.start / timing.actual_duration) * 100}%`,
                          width: `${(l.duration / timing.actual_duration) * 100}%`,
                          background: char.color,
                        }}
                      />
                    ))}
                </div>
              </div>
            ),
          )}
          <div className="timing-result">
            <CheckCircle2 size={14} />
            {timing.timing_passed
              ? "Measured dialogue fits the slots"
              : "Timing needs revision"}
          </div>
        </div>
      )}
      {version.content && file && (
        <details className="details">
          <summary>Script & artifact notes</summary>
          <div className="prose-text">{version.content}</div>
        </details>
      )}
      {compare && old && (
        <div className="compare-box">
          <div className="subheading">
            <span>PREVIOUS VERSION · V{old.number}</span>
            <Badge status={old.effective_status} />
          </div>
          {old.files[0]?.mime.startsWith("video/") ? (
            <video controls src={mediaUrl(old, 0)} />
          ) : old.files[0]?.mime.startsWith("audio/") ? (
            <audio controls src={mediaUrl(old, 0)} />
          ) : old.files[0]?.mime.startsWith("image/") ? (
            <img src={mediaUrl(old, 0)} alt="Previous version" />
          ) : null}
          <strong>Previous prompt</strong>
          <pre>{old.prompt || "No prompt saved."}</pre>
          <strong>Previous notes</strong>
          <pre>{old.content}</pre>
        </div>
      )}
      <details className="details">
        <summary>
          Source files <span>{files.length}</span>
        </summary>
        <div className="file-list">
          {files.map((f, i) => (
            <a key={i} href={mediaUrl(version, i) + "?download=true"}>
              <FileText size={14} />
              <span>
                {f.name}
                <small>{(f.size / 1024).toFixed(0)} KB</small>
              </span>
              <Download size={13} />
            </a>
          ))}
          {!files.length && (
            <p>
              Text-only artifact. The text and prompt are included in the
              project export.
            </p>
          )}
        </div>
      </details>
    </div>
  );
}

function PromptEditor({
  project,
  artifact,
  version,
  onSaved,
  onError,
  notify,
}: {
  project: Project;
  artifact: Artifact;
  version: Version;
  onSaved: (r: Json) => Promise<void>;
  onError: (s: string) => void;
  notify: (s: string) => void;
}) {
  const [prompt, setPrompt] = useState(version.prompt),
    [mapping, setMapping] = useState(version.metadata.reference_map || ""),
    [extend, setExtend] = useState(!!version.metadata.prompt_extend),
    [saving, setSaving] = useState(false),
    [content, setContent] = useState(version.content),
    [metadata, setMetadata] = useState(""),
    [pinnedInputs, setPinnedInputs] = useState<string[]>(version.inputs);
  useEffect(() => {
    setPrompt(version.prompt);
    setMapping(version.metadata.reference_map || "");
    setExtend(!!version.metadata.prompt_extend);
    setContent(version.content);
    setMetadata(JSON.stringify(version.metadata, null, 2));
    setPinnedInputs(version.inputs);
  }, [version.id]);
  const dirty =
    JSON.stringify(pinnedInputs) !== JSON.stringify(version.inputs) ||
    prompt !== version.prompt ||
    mapping !== (version.metadata.reference_map || "") ||
    extend !== !!version.metadata.prompt_extend ||
    content !== version.content ||
    metadata !== JSON.stringify(version.metadata, null, 2);
  async function save() {
    setSaving(true);
    try {
      const parsed = JSON.parse(metadata);
      const fd = new FormData();
      fd.set(
        "payload",
        JSON.stringify({
          artifact_id: artifact.id,
          expected_version: artifact.latest.id,
          title: artifact.title,
          kind: artifact.kind,
          stage: artifact.stage,
          scene_id: artifact.scene_id,
          content,
          prompt,
          metadata: {
            ...parsed,
            reference_map: mapping,
            prompt_extend: extend,
          },
          inputs: pinnedInputs,
          inherit_files: true,
        }),
      );
      await onSaved(
        await api("/projects/" + project.id + "/artifacts", "POST", fd),
      );
      notify(
        "New version saved. Earlier approvals stay with the earlier version.",
      );
    } catch (e) {
      onError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }
  return (
    <div className="prompt-column">
      <div className="subheading">
        <span>
          <Sparkles size={14} /> GENERATION PROMPT
        </span>
        <button
          className="mini-button"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(prompt);
              notify("Prompt copied.");
            } catch {
              onError(
                "Clipboard unavailable. Select and copy the prompt text.",
              );
            }
          }}
        >
          <Copy size={13} /> Copy
        </button>
      </div>
      <div className="prompt-context">
        <span className="prompt-dot" /> Exact saved prompt{" "}
        <span>v{version.number}</span>
      </div>
      <textarea
        className="prompt-textarea"
        aria-label="Generation prompt"
        value={prompt}
        placeholder="Write the exact prompt used for this artifact. Include timing, character IDs, camera, action and continuity."
        onChange={(e) => setPrompt(e.target.value)}
      />
      <div className="prompt-counter">
        {prompt.length.toLocaleString()} characters{" "}
        {dirty && <span>Unsaved edits</span>}
      </div>
      <div className="reference-mapping">
        <div className="subheading">
          <span>CHARACTER & REFERENCE MAP</span>
          <Layers size={14} />
        </div>
        <textarea
          aria-label="Character and reference mapping"
          value={mapping}
          onChange={(e) => setMapping(e.target.value)}
          placeholder="CHAR_A → blue dummy → character sheet v1\nImage 1 → identity; Video 1 → camera & motion"
        />
      </div>
      <label className="checkbox">
        <input
          type="checkbox"
          checked={extend}
          onChange={(e) => setExtend(e.target.checked)}
        />
        <span>
          Allow Wan to expand the prompt
          <small>Saved explicitly with this version.</small>
        </span>
      </label>
      <details className="details">
        <summary>Artifact text, inputs & provider metadata</summary>
        <div className="subheading">
          <span>PIN APPROVED INPUTS</span>
        </div>
        {project.artifacts
          .filter((a) => a.id !== artifact.id)
          .flatMap((a) =>
            a.versions
              .filter((v) => v.id === a.approved_version_id && !v.stale)
              .map((v) => (
                <label className="checkbox" key={v.id}>
                  <input
                    type="checkbox"
                    checked={pinnedInputs.includes(v.id)}
                    onChange={(e) =>
                      setPinnedInputs(
                        e.target.checked
                          ? [...pinnedInputs, v.id]
                          : pinnedInputs.filter((id) => id !== v.id),
                      )
                    }
                  />
                  {a.title} · v{v.number}
                </label>
              )),
          )}
        <button
          className="mini-button"
          onClick={() =>
            setPinnedInputs(
              pinnedInputs.filter((id) =>
                project.artifacts.some(
                  (a) =>
                    a.approved_version_id === id &&
                    !a.versions.find((v) => v.id === id)?.stale,
                ),
              ),
            )
          }
        >
          Remove outdated source pins
        </button>
        <Field label="Artifact text">
          <textarea
            rows={7}
            value={content}
            onChange={(e) => setContent(e.target.value)}
          />
        </Field>
        <Field
          label="Metadata (JSON)"
          hint="Ordered reference_media, measured duration and provider settings. Mapping and prompt expansion above take precedence."
        >
          <textarea
            className="code-text"
            rows={9}
            value={metadata}
            onChange={(e) => setMetadata(e.target.value)}
          />
        </Field>
      </details>
      <button
        className="button primary save-prompt"
        disabled={!dirty || saving}
        onClick={save}
      >
        {saving ? (
          <LoaderCircle className="spin" size={15} />
        ) : (
          <Save size={15} />
        )}{" "}
        Save as new version
      </button>
      <p className="tiny-note">
        Edits create a new version. Review the saved version before moving to
        the next stage.
      </p>
    </div>
  );
}

function ReviewPanel({
  project,
  artifact,
  version,
  busy,
  act,
}: {
  project: Project;
  artifact: Artifact;
  version: Version;
  busy: boolean;
  act: (fn: () => Promise<unknown>, message?: string) => Promise<void>;
}) {
  const [checks, setChecks] = useState<Json | null>(null),
    [note, setNote] = useState(""),
    [time, setTime] = useState(""),
    [anchorPage, setAnchorPage] = useState("");
  useEffect(() => {
    let valid = true;
    setChecks(null);
    setNote("");
    setTime("");
    setAnchorPage("");
    api("/versions/" + version.id + "/checks")
      .then((v) => valid && setChecks(v))
      .catch(
        (e) =>
          valid &&
          setChecks({ passed: false, issues: [e.message], checks: [] }),
      );
    return () => {
      valid = false;
    };
  }, [version.id, version.stale]);
  function review(decision: string) {
    return act(
      async () => {
        await api("/versions/" + version.id + "/review", "POST", {
          decision,
          note,
          anchor: {
            ...(time !== "" ? { seconds: Number(time) } : {}),
            ...(anchorPage ? { page: Number(anchorPage) } : {}),
          },
        });
        setNote("");
      },
      decision === "approved"
        ? "Version approved. The workflow has been updated."
        : "Feedback saved on this version.",
    );
  }
  const inputNames = version.inputs.map((id) => {
    const a = project.artifacts.find((a) =>
      a.versions.some((v) => v.id === id),
    );
    const v = a?.versions.find((v) => v.id === id);
    return `${a?.title || id} · v${v?.number || "?"}`;
  });
  return (
    <div className="panel review-card">
      <div className="panel-heading">
        <ListChecks size={18} />
        <h3>Review package</h3>
        <span className="micro">V{version.number}</span>
      </div>
      <div className="panel-body">
        <Badge status={version.effective_status} />
        <p className="review-instruction">
          Review the preview, prompt and reference mapping together.
        </p>
        <div className="check-section">
          <div className="subheading">
            <span>TECHNICAL CHECKS</span>
          </div>
          {!checks ? (
            <span className="muted">Checking…</span>
          ) : (
            <>
              {checks.checks?.map((c: string) => (
                <div className="check-line" key={c}>
                  <CheckCircle2 size={15} />
                  <span>{c}</span>
                </div>
              ))}
              {checks.issues?.map((c: string) => (
                <div className="check-line issue" key={c}>
                  <AlertCircle size={15} />
                  <span>{c}</span>
                </div>
              ))}
            </>
          )}
        </div>
        <div className="source-links">
          <div className="subheading">
            <span>PINNED SOURCES</span>
            <span>{inputNames.length}</span>
          </div>
          {inputNames.length ? (
            inputNames.map((n) => (
              <div key={n}>
                <Layers size={12} />
                {n}
              </div>
            ))
          ) : (
            <p>No upstream versions attached.</p>
          )}
        </div>
        <Field label="Director’s feedback">
          <textarea
            rows={3}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="What works? What should change?"
          />
        </Field>
        <div className="form-row">
          <Field label="Timecode (s)">
            <input
              type="number"
              step="0.1"
              min="0"
              placeholder="Optional"
              value={time}
              onChange={(e) => setTime(e.target.value)}
            />
          </Field>
          <Field label="Page / frame">
            <input
              type="number"
              min="1"
              placeholder="Optional"
              value={anchorPage}
              onChange={(e) => setAnchorPage(e.target.value)}
            />
          </Field>
        </div>
        <button
          className="button primary approve-button"
          disabled={busy || !checks?.passed || version.status === "approved"}
          onClick={() => review("approved")}
        >
          <Check size={16} /> Approve v{version.number}
        </button>
        <div className="review-buttons">
          <button
            className="button secondary"
            disabled={busy || !note.trim()}
            onClick={() => review("changes_requested")}
          >
            Request changes
          </button>
          <button
            className="icon-button comment-button"
            aria-label="Save comment"
            disabled={busy || !note.trim()}
            onClick={() => review("comment")}
          >
            <MessageSquare size={17} />
          </button>
        </div>
        {version.status === "draft" && (
          <button
            className="button text-button submit-button"
            disabled={busy || !checks?.passed}
            onClick={() =>
              act(
                () => api("/versions/" + version.id + "/submit", "POST"),
                "Version added to your review queue.",
              )
            }
          >
            Submit for review <ArrowUpRight size={14} />
          </button>
        )}
        <p className="tiny-note">
          Technical checks support your review. Approval is your creative
          decision.
        </p>
        {version.reviews.length > 0 && (
          <div className="review-history">
            <div className="subheading">
              <span>VERSION FEEDBACK</span>
            </div>
            {version.reviews.map((r) => (
              <div key={r.id} className="review-note">
                <strong>
                  {statusLabels[r.decision] || "Comment"}
                  {r.anchor.seconds != null ? ` · ${r.anchor.seconds}s` : ""}
                  {r.anchor.page ? ` · frame ${r.anchor.page}` : ""}
                </strong>
                <p>{r.note || "Approved by director."}</p>
                <small>{new Date(r.created).toLocaleString()}</small>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function JobList({ project }: { project: Project }) {
  return (
    <div className="job-list">
      {[...project.jobs, ...project.tasks].map((j) => (
        <div className="job-row" key={j.id}>
          {["running", "queued"].includes(j.status) ? (
            <LoaderCircle size={16} className="spin" />
          ) : (
            <Terminal size={16} />
          )}
          <div>
            <strong>
              {j.kind?.replaceAll("_", " ") || j.owner + " · " + j.stage}
            </strong>
            <small>
              {j.data?.message || j.data?.issues?.join(" ") || j.id}
            </small>
          </div>
          <Badge
            status={
              j.status === "claimed" && j.expires * 1000 < Date.now()
                ? "expired"
                : j.status
            }
          />
        </div>
      ))}
      {!project.jobs.length && !project.tasks.length && (
        <p className="muted">
          No active jobs. The next agent handoff appears in Workflow & agents.
        </p>
      )}
    </div>
  );
}

function Timeline({
  project,
  refresh,
  onError,
  notify,
}: {
  project: Project;
  refresh: () => Promise<void>;
  onError: (v: string) => void;
  notify: (v: string) => void;
}) {
  const [entries, setEntries] = useState<Json[]>(project.timeline),
    [choice, setChoice] = useState(""),
    [playing, setPlaying] = useState(false),
    [active, setActive] = useState(0),
    [saving, setSaving] = useState(false);
  const player = useRef<HTMLVideoElement>(null);
  useEffect(
    () => setEntries(project.timeline),
    [
      project.id,
      JSON.stringify(
        project.timeline.map((e) => [e.version_id, e.in, e.out, e.ordinal]),
      ),
    ],
  );
  const candidates = project.artifacts.flatMap((a) =>
    a.versions.flatMap((v) =>
      v.files
        .map((f, i) => ({ a, v, f, i }))
        .filter(
          (x) => x.f.mime.startsWith("video/") || x.f.mime.startsWith("audio/"),
        ),
    ),
  );
  const current = entries[active];
  function advance() {
    if (active + 1 < entries.length) setActive(active + 1);
    else {
      setPlaying(false);
      player.current?.pause();
    }
  }
  const total = entries.reduce((n, e) => n + e.out - e.in, 0);
  async function save() {
    setSaving(true);
    try {
      await api("/projects/" + project.id + "/timeline", "PUT", {
        entries,
        expected_revision: project.revision,
      });
      await refresh();
      notify("Rough cut saved.");
    } catch (e) {
      onError(String(e));
    } finally {
      setSaving(false);
    }
  }
  return (
    <section className="timeline-layout">
      <div className="panel timeline-player">
        <div className="panel-heading">
          <Film size={18} />
          <h3>Continuous rough cut</h3>
          <span className="micro">{total.toFixed(1)}s</span>
        </div>
        <div className="timeline-screen">
          {current ? (
            <video
              ref={player}
              key={current.version_id + active + current.file_index}
              controls
              src={`/api/media/${current.version_id}/${current.file_index}`}
              onLoadedMetadata={(e) => {
                e.currentTarget.currentTime = current.in;
                if (playing)
                  e.currentTarget.play().catch(() => setPlaying(false));
              }}
              onTimeUpdate={(e) => {
                if (playing && e.currentTarget.currentTime >= current.out) {
                  e.currentTarget.pause();
                  advance();
                }
              }}
              onEnded={() => {
                if (playing) advance();
              }}
            />
          ) : (
            <Empty icon={Film} title="Find the rhythm of the film">
              Choose takes below, trim usable ranges, and play them in sequence.
            </Empty>
          )}
        </div>
        <div className="timeline-controls">
          <button
            className="button primary"
            disabled={!entries.length}
            onClick={() => {
              setActive(0);
              setPlaying(true);
              if (active === 0 && player.current) {
                player.current.currentTime = entries[0].in;
                player.current.play().catch(() => setPlaying(false));
              }
            }}
          >
            <Play size={15} /> Play sequence
          </button>
          <span>
            {playing
              ? `Playing ${active + 1} of ${entries.length}`
              : "Browser rough cut · hard cuts"}
          </span>
        </div>
        <p className="tiny-note">
          Use this to review order and pacing. Seamless mastering, audio
          overlaps and final mixing belong in the final edit.
        </p>
      </div>
      <div className="panel timeline-editor">
        <div className="panel-heading">
          <Layers size={18} />
          <h3>Selected takes</h3>
          <button
            className="mini-button"
            onClick={() => downloadJson(entries, "rough-cut-timeline.json")}
          >
            <Download size={14} /> JSON
          </button>
        </div>
        <div className="panel-body">
          <div className="timeline-add">
            <select
              aria-label="Take to add"
              value={choice}
              onChange={(e) => setChoice(e.target.value)}
            >
              <option value="">Choose a take or audio track</option>
              {candidates.map((c) => (
                <option key={c.v.id + ":" + c.i} value={c.v.id + ":" + c.i}>
                  {c.a.title} · v{c.v.number} · {c.f.name} ·{" "}
                  {c.v.effective_status}
                </option>
              ))}
            </select>
            <button
              className="button secondary"
              aria-label="Add selected take"
              disabled={!choice}
              onClick={() => {
                const c = candidates.find(
                  (c) => c.v.id + ":" + c.i === choice,
                )!;
                if (!c.v.metadata.duration) {
                  onError(
                    "This take needs a measured duration. Re-import it or add its measured duration to metadata.",
                  );
                  return;
                }
                setEntries([
                  ...entries,
                  {
                    version_id: c.v.id,
                    file_index: c.i,
                    in: 0,
                    out: c.v.metadata.duration,
                    label: c.a.title,
                    version: c.v,
                  },
                ]);
              }}
            >
              <Plus size={15} />
            </button>
          </div>
          {entries.map((e, i) => (
            <div key={i} className="cut-row">
              <button
                className="cut-index"
                onClick={() => {
                  setActive(i);
                  setPlaying(false);
                }}
              >
                {String(i + 1).padStart(2, "0")}
              </button>
              <div className="cut-detail">
                <strong>{e.label}</strong>
                <Badge status={e.version?.effective_status || "draft"} />
                <div className="cut-range">
                  <label>
                    IN{" "}
                    <input
                      aria-label={`Clip ${i + 1} in point`}
                      type="number"
                      step="0.1"
                      min="0"
                      value={e.in}
                      onChange={(ev) =>
                        setEntries(
                          entries.map((x, n) =>
                            n === i ? { ...x, in: +ev.target.value } : x,
                          ),
                        )
                      }
                    />
                  </label>
                  <label>
                    OUT{" "}
                    <input
                      aria-label={`Clip ${i + 1} out point`}
                      type="number"
                      step="0.1"
                      min="0"
                      value={e.out}
                      onChange={(ev) =>
                        setEntries(
                          entries.map((x, n) =>
                            n === i ? { ...x, out: +ev.target.value } : x,
                          ),
                        )
                      }
                    />
                  </label>
                  <span>{(e.out - e.in).toFixed(1)}s</span>
                </div>
              </div>
              <div className="cut-actions">
                <button
                  className="icon-button"
                  aria-label={`Move clip ${i + 1} up`}
                  disabled={!i}
                  onClick={() => {
                    const copy = [...entries];
                    [copy[i - 1], copy[i]] = [copy[i], copy[i - 1]];
                    setEntries(copy);
                  }}
                >
                  <ArrowUp size={14} />
                </button>
                <button
                  className="icon-button"
                  aria-label={`Move clip ${i + 1} down`}
                  disabled={i === entries.length - 1}
                  onClick={() => {
                    const copy = [...entries];
                    [copy[i + 1], copy[i]] = [copy[i], copy[i + 1]];
                    setEntries(copy);
                  }}
                >
                  <ArrowDown size={14} />
                </button>
                <button
                  className="icon-button"
                  aria-label={`Remove clip ${i + 1}`}
                  onClick={() => setEntries(entries.filter((_, n) => n !== i))}
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          ))}
          <button className="button primary" disabled={saving} onClick={save}>
            <Save size={15} /> Save rough cut
          </button>
        </div>
      </div>
    </section>
  );
}

function useForm() {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  return { busy, error, run };
}
function FormError({ error }: { error: string }) {
  return error ? (
    <div role="alert" className="alert error">
      {error}
    </div>
  ) : null;
}
function ProjectForm({
  onClose,
  onSaved,
}: {
  onClose: () => void;
  onSaved: (p: Project) => Promise<void>;
}) {
  const [title, setTitle] = useState(""),
    [brief, setBrief] = useState(""),
    [runtime, setRuntime] = useState(2),
    [ratio, setRatio] = useState("16:9");
  const f = useForm();
  return (
    <Modal
      title="Start a new project"
      subtitle="Give your agents a clear starting point."
      onClose={onClose}
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          f.run(async () =>
            onSaved(
              await api("/projects", "POST", {
                title,
                brief,
                runtime_minutes: runtime,
                aspect_ratio: ratio,
              }),
            ),
          );
        }}
      >
        <div className="form-body">
          <FormError error={f.error} />
          <Field label="Project title">
            <input
              autoFocus
              required
              maxLength={120}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="The working title of your film"
            />
          </Field>
          <Field label="Creative brief">
            <textarea
              rows={4}
              value={brief}
              onChange={(e) => setBrief(e.target.value)}
              placeholder="Audience, genre, emotional journey, constraints…"
            />
          </Field>
          <div className="form-row">
            <Field label="Target runtime (minutes)">
              <input
                type="number"
                min="0.25"
                max="240"
                step="0.25"
                value={runtime}
                onChange={(e) => setRuntime(+e.target.value)}
              />
            </Field>
            <Field label="Aspect ratio">
              <select value={ratio} onChange={(e) => setRatio(e.target.value)}>
                <option>16:9</option>
                <option>9:16</option>
                <option>1:1</option>
              </select>
            </Field>
          </div>
          <p className="callout">
            Your project starts at the premise gate. Generation packages are
            2–15 seconds at 30 fps.
          </p>
        </div>
        <FormFooter busy={f.busy} onClose={onClose} label="Create project" />
      </form>
    </Modal>
  );
}
function ArtifactForm({
  project,
  stage,
  sceneId,
  onClose,
  onSaved,
}: {
  project: Project;
  stage: string;
  sceneId: string;
  onClose: () => void;
  onSaved: (r: Json) => Promise<void>;
}) {
  const [s, setS] = useState(stage),
    [kind, setKind] = useState(
      project.stage_status.find((x) => x.id === stage)?.kind || "notes",
    ),
    [scene, setScene] = useState(sceneId),
    [title, setTitle] = useState(""),
    [content, setContent] = useState(""),
    [prompt, setPrompt] = useState(""),
    [metadata, setMetadata] = useState("{}"),
    [inputs, setInputs] = useState<string[]>([]),
    [files, setFiles] = useState<File[]>([]);
  const f = useForm();
  const approved = project.artifacts.flatMap((a) =>
    a.versions
      .filter((v) => v.id === a.approved_version_id && !v.stale)
      .map((v) => ({ a, v })),
  );
  useEffect(() => {
    setInputs(
      approved
        .filter(
          (x) =>
            project.stage_status.findIndex((q) => q.id === x.a.stage) <
              project.stage_status.findIndex((q) => q.id === s) &&
            (!x.a.scene_id || x.a.scene_id === scene),
        )
        .map((x) => x.v.id),
    );
  }, [s, scene]);
  return (
    <Modal
      wide
      title="Add an artifact"
      subtitle="Save the result and the exact prompt as one reviewable version."
      onClose={onClose}
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          f.run(async () => {
            const fd = new FormData();
            fd.set(
              "payload",
              JSON.stringify({
                title,
                kind,
                stage: s,
                scene_id: scene || null,
                content,
                prompt,
                metadata: JSON.parse(metadata),
                inputs,
              }),
            );
            files.forEach((file) => fd.append("files", file));
            await onSaved(
              await api("/projects/" + project.id + "/artifacts", "POST", fd),
            );
          });
        }}
      >
        <div className="form-body">
          <FormError error={f.error} />
          <div className="form-row">
            <Field label="Workflow stage">
              <select
                value={s}
                onChange={(e) => {
                  setS(e.target.value);
                  setKind(
                    project.stage_status.find((x) => x.id === e.target.value)!
                      .kind,
                  );
                }}
              >
                {project.stage_status.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Artifact kind">
              <select value={kind} onChange={(e) => setKind(e.target.value)}>
                {[
                  "premise",
                  "comic",
                  "script",
                  "audio",
                  "storyboard",
                  "reference",
                  "previs",
                  "video",
                  "edit",
                  "prompt",
                  "notes",
                ].map((k) => (
                  <option key={k}>{k}</option>
                ))}
              </select>
            </Field>
            <Field label="Scope">
              <select value={scene} onChange={(e) => setScene(e.target.value)}>
                <option value="">Whole project</option>
                {project.scenes.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.title}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <Field label="Artifact title">
            <input
              required
              autoFocus
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="A premise, a ten-page comic, a storyboard package…"
            />
          </Field>
          <div className="form-row">
            <Field label="Readable content / notes">
              <textarea
                rows={8}
                value={content}
                onChange={(e) => setContent(e.target.value)}
                placeholder="The actual story, script or notes to review."
              />
            </Field>
            <Field label="Exact generation prompt">
              <textarea
                rows={8}
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder="Prompt text, shot timing, action, camera and references."
              />
            </Field>
          </div>
          <Field
            label="Attach source files"
            hint="Comic: select all 10 page images in reading order. Audio/video duration is measured on import. 200 MB per file."
          >
            <input
              type="file"
              multiple
              accept=".png,.jpg,.jpeg,.webp,.pdf,.mp4,.webm,.mov,.wav,.mp3,.m4a,.json,.txt,.md,.csv,.srt,.blend"
              onChange={(e) => setFiles(Array.from(e.target.files || []))}
            />
          </Field>
          {files.length > 0 && (
            <div className="selected-files">
              {files.map((file, i) => (
                <span key={i}>
                  {i + 1}. {file.name}
                </span>
              ))}
            </div>
          )}
          <details className="details">
            <summary>
              Pinned inputs & metadata ({inputs.length} sources)
            </summary>
            {approved.map(({ a, v }) => (
              <label className="checkbox" key={v.id}>
                <input
                  type="checkbox"
                  checked={inputs.includes(v.id)}
                  onChange={(e) =>
                    setInputs(
                      e.target.checked
                        ? [...inputs, v.id]
                        : inputs.filter((x) => x !== v.id),
                    )
                  }
                />
                {a.title} · v{v.number}
              </label>
            ))}
            <Field label="Metadata JSON">
              <textarea
                className="code-text"
                rows={5}
                value={metadata}
                onChange={(e) => setMetadata(e.target.value)}
              />
            </Field>
          </details>
        </div>
        <FormFooter busy={f.busy} onClose={onClose} label="Save version" />
      </form>
    </Modal>
  );
}
function SceneForm({
  project,
  scene,
  onClose,
  onSaved,
}: {
  project: Project;
  scene?: Scene;
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const [data, setData] = useState<Json>(
    scene || {
      title: "",
      duration: 15,
      purpose: "",
      emotion: "",
      start_state: "",
      end_state: "",
      locked: "",
      flexible: "",
      voice_notes: "",
    },
  );
  const f = useForm();
  return (
    <Modal
      wide
      title={scene ? "Scene direction" : "New scene package"}
      subtitle="Define what must happen, what changes, and what the AI may explore."
      onClose={onClose}
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          f.run(async () => {
            await api(
              "/projects/" +
                project.id +
                "/scenes" +
                (scene ? "/" + scene.id : ""),
              scene ? "PATCH" : "POST",
              { ...data, expected_revision: scene?.revision },
            );
            await onSaved();
          });
        }}
      >
        <div className="form-body">
          <FormError error={f.error} />
          {scene && (
            <p className="callout">
              Changing direction marks versions made against the previous
              direction as needing an update.
            </p>
          )}
          <div className="form-row">
            <Field label="Package title">
              <input
                autoFocus
                required
                value={data.title}
                onChange={(e) => setData({ ...data, title: e.target.value })}
              />
            </Field>
            <Field label="Duration (seconds)">
              <input
                type="number"
                min="2"
                max="15"
                step="1"
                required
                value={data.duration}
                onChange={(e) =>
                  setData({ ...data, duration: +e.target.value })
                }
              />
            </Field>
          </div>
          <div className="form-row">
            {[
              ["purpose", "Dramatic purpose"],
              ["emotion", "Emotional turn"],
              ["start_state", "Start state / continuity"],
              ["end_state", "End state / continuity"],
              ["locked", "Locked decisions"],
              ["flexible", "Open to exploration"],
            ].map(([key, label]) => (
              <Field key={key} label={label}>
                <textarea
                  rows={3}
                  value={data[key]}
                  onChange={(e) => setData({ ...data, [key]: e.target.value })}
                />
              </Field>
            ))}
          </div>
          <Field label="Voice & performance direction">
            <textarea
              rows={2}
              value={data.voice_notes}
              onChange={(e) =>
                setData({ ...data, voice_notes: e.target.value })
              }
            />
          </Field>
        </div>
        <FormFooter busy={f.busy} onClose={onClose} label="Save direction" />
      </form>
    </Modal>
  );
}
function DirectionForm({
  project,
  onClose,
  onSaved,
}: {
  project: Project;
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const [data, setData] = useState<Json>({
    title: project.title,
    brief: project.brief,
    ...project.settings,
  });
  const f = useForm();
  return (
    <Modal
      wide
      title="Project direction"
      subtitle="The decisions that keep every collaborator working on the same film."
      onClose={onClose}
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          f.run(async () => {
            await api("/projects/" + project.id, "PATCH", {
              ...data,
              expected_revision: project.revision,
            });
            await onSaved();
          });
        }}
      >
        <div className="form-body">
          <FormError error={f.error} />
          <Field label="Working title">
            <input
              required
              value={data.title}
              onChange={(e) => setData({ ...data, title: e.target.value })}
            />
          </Field>
          {[
            ["brief", "Creative brief"],
            ["creative_locks", "Creative locks"],
            ["world_notes", "Story world & continuity bible"],
            ["voice_direction", "Cast & voice direction"],
            ["delivery_notes", "Delivery, credits & source rights"],
          ].map(([key, label]) => (
            <Field key={key} label={label}>
              <textarea
                rows={3}
                value={data[key] || ""}
                onChange={(e) => setData({ ...data, [key]: e.target.value })}
              />
            </Field>
          ))}
          <Field
            label="Planning budget (USD)"
            hint="A planning number, not permission to spend. No paid requests are sent by this version of the studio."
          >
            <input
              type="number"
              min="0"
              max="100000"
              value={data.budget}
              onChange={(e) => setData({ ...data, budget: +e.target.value })}
            />
          </Field>
        </div>
        <FormFooter busy={f.busy} onClose={onClose} />
      </form>
    </Modal>
  );
}
function AudioForm({
  project,
  initialScene,
  onClose,
  onSaved,
}: {
  project: Project;
  initialScene?: string;
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const [scene, setScene] = useState(initialScene || ""),
    [source, setSource] = useState(""),
    [advanced, setAdvanced] = useState(false);
  const f = useForm();
  useEffect(() => {
    api("/audio-template")
      .then((data) => {
        data.title =
          "Temporary dialogue · " +
          (project.scenes.find((s) => s.id === scene)?.title || "scene");
        data.sequence_id = "SCRATCH";
        data.generation_prompt = "";
        setSource(JSON.stringify(data, null, 2));
      })
      .catch((e) =>
        f.run(async () => {
          throw e;
        }),
      );
  }, []);
  let parsed: Json | null = null;
  try {
    parsed = JSON.parse(source);
  } catch {}
  function changeLine(i: number, key: string, value: unknown) {
    if (!parsed) return;
    const p = structuredClone(parsed);
    p.lines[i][key] = value;
    setSource(JSON.stringify(p, null, 2));
  }
  return (
    <Modal
      wide
      title="Generate temporary dialogue"
      subtitle="Local Windows voices, measured timing, separate tracks. No API credits."
      onClose={onClose}
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          f.run(async () => {
            await api("/projects/" + project.id + "/audio", "POST", {
              scene_id: scene,
              source: JSON.parse(source),
            });
            await onSaved();
          });
        }}
      >
        <div className="form-body">
          <FormError error={f.error} />
          {!project.scenes.length ? (
            <p className="callout">
              Create a scene package first, then add its dialogue here.
            </p>
          ) : (
            <Field label="Scene package">
              <select
                required
                value={scene}
                onChange={(e) => setScene(e.target.value)}
              >
                <option value="">Choose a package</option>
                {project.scenes.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.title} · {s.duration}s
                  </option>
                ))}
              </select>
            </Field>
          )}
          <p className="callout">
            The starter timing is 15 seconds: two voices, an opening beat, a
            reaction, and an ending hold. Edit all timing and cast settings in
            the JSON for other packages.
          </p>
          {parsed?.lines?.map((line: Json, i: number) => (
            <div className="audio-line-form" key={i}>
              <div className="subheading">
                <span>
                  {line.character} · {parsed?.characters[line.character]?.voice}
                </span>
              </div>
              <Field label={"Line " + (i + 1)}>
                <textarea
                  rows={2}
                  value={line.text}
                  onChange={(e) => changeLine(i, "text", e.target.value)}
                />
              </Field>
              <div className="form-row">
                <Field label="Starts at (s)">
                  <input
                    type="number"
                    step="0.1"
                    value={line.start}
                    onChange={(e) => changeLine(i, "start", +e.target.value)}
                  />
                </Field>
                <Field label="Must finish by (s)">
                  <input
                    type="number"
                    step="0.1"
                    value={line.slot_end}
                    onChange={(e) => changeLine(i, "slot_end", +e.target.value)}
                  />
                </Field>
              </div>
            </div>
          ))}
          <button
            type="button"
            className="button text-button"
            onClick={() => setAdvanced(!advanced)}
          >
            <Terminal size={15} /> {advanced ? "Hide" : "Edit"} full timing
            source
          </button>
          {advanced && (
            <Field label="Source JSON">
              <textarea
                className="code-text"
                rows={18}
                value={source}
                onChange={(e) => setSource(e.target.value)}
              />
            </Field>
          )}
          <p className="tiny-note">
            If speech overruns its slot, the full line is kept and the result is
            marked for changes. Passing timing still needs your creative review.
          </p>
        </div>
        <FormFooter
          busy={f.busy || !project.scenes.length}
          onClose={onClose}
          label="Generate scratch audio"
        />
      </form>
    </Modal>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
