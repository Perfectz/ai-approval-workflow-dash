from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import mimetypes
import os
from pathlib import Path
import shutil
import sqlite3
import time
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = json.loads((ROOT / "workflows/comic-to-wan-v1.json").read_text(encoding="utf-8"))
STAGES = [s["id"] for s in WORKFLOW["stages"]]
KINDS = {"premise", "comic", "script", "audio", "storyboard", "reference", "previs", "video", "edit", "prompt", "notes"}
EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".pdf", ".mp4", ".webm", ".mov", ".wav", ".mp3", ".m4a", ".json", ".txt", ".md", ".csv", ".srt", ".blend"}


class Problem(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def ident(prefix):
    return prefix + "_" + uuid.uuid4().hex[:16]


def now():
    return datetime.now(timezone.utc).isoformat()


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def direction_hash(project):
    value = {"brief": project["brief"], **{key: project["settings"].get(key, "") for key in ("creative_locks", "world_notes", "voice_direction")}}
    return hashlib.sha256(encode(value).encode()).hexdigest()


def text(value, name, limit=100000, required=False):
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise Problem(f"{name} must be {'non-empty ' if required else ''}text, up to {limit} characters.")
    return value.strip()


def numeric(value, name, lower, upper):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lower <= value <= upper:
        raise Problem(f"{name} must be between {lower} and {upper}.")
    return value


class Store:
    def __init__(self, directory=None):
        self.root = Path(directory or os.environ.get("DIRECTOR_DATA", ROOT / "studio-data")).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "studio.sqlite"
        with self.db() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,title TEXT NOT NULL,brief TEXT NOT NULL,settings TEXT NOT NULL,created TEXT NOT NULL,revision INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS scenes(id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES projects(id),ordinal INTEGER NOT NULL,data TEXT NOT NULL,revision INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS artifacts(id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES projects(id),scene_id TEXT REFERENCES scenes(id),kind TEXT NOT NULL,stage TEXT NOT NULL,title TEXT NOT NULL,created TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS versions(id TEXT PRIMARY KEY,artifact_id TEXT NOT NULL REFERENCES artifacts(id),number INTEGER NOT NULL,data TEXT NOT NULL,created TEXT NOT NULL,UNIQUE(artifact_id,number));
            CREATE TABLE IF NOT EXISTS reviews(id TEXT PRIMARY KEY,version_id TEXT NOT NULL REFERENCES versions(id),decision TEXT NOT NULL,note TEXT NOT NULL,anchor TEXT NOT NULL,created TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES projects(id),scene_id TEXT,stage TEXT NOT NULL,owner TEXT NOT NULL,token TEXT NOT NULL,expires REAL NOT NULL,status TEXT NOT NULL,inputs TEXT NOT NULL,created TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS task_context(task_id TEXT PRIMARY KEY REFERENCES tasks(id),data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS timeline(id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES projects(id),version_id TEXT NOT NULL REFERENCES versions(id),ordinal INTEGER NOT NULL,data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,project_id TEXT NOT NULL,kind TEXT NOT NULL,message TEXT NOT NULL,actor TEXT NOT NULL,created TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,scene_id TEXT,kind TEXT NOT NULL,status TEXT NOT NULL,data TEXT NOT NULL,created TEXT NOT NULL,updated TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS artifact_project ON artifacts(project_id);
            CREATE INDEX IF NOT EXISTS review_version ON reviews(version_id);
            """)

    @contextmanager
    def db(self, write=False):
        db = sqlite3.connect(self.db_path, timeout=20)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA journal_mode=WAL")
        try:
            if write:
                db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def required(self, db, table, key):
        row = db.execute(f"SELECT * FROM {table} WHERE id=?", (key,)).fetchone()
        if row is None:
            raise Problem(f"{table.rstrip('s').capitalize()} not found.", 404)
        return dict(row)

    def event(self, db, project, kind, message, actor="director"):
        db.execute("INSERT INTO events(project_id,kind,message,actor,created) VALUES(?,?,?,?,?)", (project, kind, message, actor, now()))

    def create_project(self, payload):
        title = text(payload.get("title", ""), "Project title", 120, True)
        brief = text(payload.get("brief", ""), "Brief")
        settings = {"runtime_minutes": numeric(payload.get("runtime_minutes", 2), "Runtime", .25, 240), "aspect_ratio": payload.get("aspect_ratio", "16:9"), "workflow_id": WORKFLOW["id"], "workflow_version": 1, "budget": numeric(payload.get("budget", 0), "Budget", 0, 100000), "demo": bool(payload.get("demo", False))}
        if settings["aspect_ratio"] not in ("16:9", "9:16", "1:1"):
            raise Problem("Choose a supported aspect ratio.")
        key = ident("project")
        with self.db(True) as db:
            db.execute("INSERT INTO projects(id,title,brief,settings,created) VALUES(?,?,?,?,?)", (key, title, brief, encode(settings), now()))
            self.event(db, key, "project", f"Created {title}")
        return self.project(key)

    def list_projects(self):
        with self.db() as db:
            ids = [r[0] for r in db.execute("SELECT id FROM projects ORDER BY created DESC")]
        result = []
        for key in ids:
            project = self.project(key)
            result.append({k: project[k] for k in ("id", "title", "brief", "settings", "created", "revision", "stage_status", "review_count", "artifact_count", "scene_count")})
        return result

    def update_project(self, key, payload):
        with self.db(True) as db:
            p = self.required(db, "projects", key)
            if payload.get("expected_revision") != p["revision"]:
                raise Problem("This project changed. Refresh before saving.", 409)
            settings = json.loads(p["settings"])
            for field in ("creative_locks", "voice_direction", "delivery_notes", "world_notes"):
                if field in payload:
                    settings[field] = text(payload[field], field)
            if "budget" in payload:
                settings["budget"] = numeric(payload["budget"], "Budget", 0, 100000)
            db.execute("UPDATE projects SET title=?,brief=?,settings=?,revision=revision+1 WHERE id=?", (text(payload.get("title", p["title"]), "Title", 120, True), text(payload.get("brief", p["brief"]), "Brief"), encode(settings), key))
            self.event(db, key, "direction", "Updated project direction")
        return self.project(key)

    def save_scene(self, project, payload, key=None):
        with self.db(True) as db:
            self.required(db, "projects", project)
            old = self.required(db, "scenes", key) if key else None
            if old and (old["project_id"] != project or payload.get("expected_revision") != old["revision"]):
                raise Problem("Scene changed or belongs to another project.", 409)
            value = json.loads(old["data"]) if old else {}
            for field in ("title", "purpose", "emotion", "start_state", "end_state", "locked", "flexible", "voice_notes"):
                value[field] = text(payload.get(field, value.get(field, "")), field, 120 if field == "title" else 10000, field == "title")
            value["duration"] = numeric(payload.get("duration", value.get("duration", 15)), "Package duration", 2, 15)
            if int(value["duration"]) != value["duration"]:
                raise Problem("Generation package duration must be a whole number of seconds.")
            if old:
                db.execute("UPDATE scenes SET data=?,revision=revision+1 WHERE id=?", (encode(value), key))
            else:
                key = ident("scene")
                ordinal = db.execute("SELECT COALESCE(MAX(ordinal),0)+1 FROM scenes WHERE project_id=?", (project,)).fetchone()[0]
                db.execute("INSERT INTO scenes(id,project_id,ordinal,data) VALUES(?,?,?,?)", (key, project, ordinal, encode(value)))
            self.event(db, project, "scene", f"{'Updated' if old else 'Created'} {value['title']}")
        return key

    def project(self, key):
        with self.db() as db:
            return self._project(db, key)

    def _project(self, db, key):
        p = self.required(db, "projects", key)
        p["settings"] = json.loads(p["settings"])
        p["scenes"] = [{**dict(r), **json.loads(r["data"])} for r in db.execute("SELECT * FROM scenes WHERE project_id=? ORDER BY ordinal", (key,))]
        p["artifacts"] = [dict(r) for r in db.execute("SELECT * FROM artifacts WHERE project_id=? ORDER BY created", (key,))]
        versions, approved = {}, {}
        for artifact in p["artifacts"]:
            artifact["versions"] = []
            for row in db.execute("SELECT * FROM versions WHERE artifact_id=? ORDER BY number DESC", (artifact["id"],)):
                v = {**dict(row), **json.loads(row["data"])}
                v.pop("data", None)
                v["reviews"] = [{**dict(r), "anchor": json.loads(r["anchor"])} for r in db.execute("SELECT * FROM reviews WHERE version_id=? ORDER BY rowid DESC", (v["id"],))]
                decision = next((r["decision"] for r in v["reviews"] if r["decision"] != "comment"), None)
                v["status"] = decision or ("in_review" if v.get("submitted") else "draft")
                v["artifact_id"] = artifact["id"]
                versions[v["id"]] = v
                if decision == "approved" and artifact["id"] not in approved:
                    approved[artifact["id"]] = v["id"]
                artifact["versions"].append(v)
        def stale(version_id, trail=None):
            trail = set(trail or ())
            if version_id in trail:
                return True
            trail.add(version_id)
            v = versions.get(version_id)
            if not v:
                return True
            if v.get("direction_hash") and v["direction_hash"] != direction_hash(p):
                return True
            for source in v.get("inputs", []):
                dep = versions.get(source)
                if not dep or approved.get(dep["artifact_id"]) != source or stale(source, trail):
                    return True
            scene_id = v.get("scene_id")
            scene = next((s for s in p["scenes"] if s["id"] == scene_id), None)
            if scene and v.get("scene_revision") and scene["revision"] != v["scene_revision"]:
                return True
            return False
        for v in versions.values():
            v["stale"] = stale(v["id"])
            v["effective_status"] = "needs_update" if v["stale"] else v["status"]
        for a in p["artifacts"]:
            a["latest"] = a["versions"][0] if a["versions"] else None
            a["approved_version_id"] = approved.get(a["id"])
        stage_status = []
        for stage in WORKFLOW["stages"]:
            relevant = [a for a in p["artifacts"] if a["stage"] == stage["id"] and a["kind"] == stage["kind"]]
            good = [a for a in relevant if a["approved_version_id"] and not versions[a["approved_version_id"]]["stale"]]
            if stage["scope"] == "scene":
                complete = bool(p["scenes"]) and all(any(a["scene_id"] == s["id"] for a in good) for s in p["scenes"])
            else:
                complete = bool(good)
            stage_status.append({**stage, "complete": complete, "count": len(relevant), "approved_count": len(good)})
        p["stage_status"] = stage_status
        p["review_count"] = sum(1 for a in p["artifacts"] if a["latest"] and a["latest"]["effective_status"] == "in_review")
        p["artifact_count"], p["scene_count"] = len(p["artifacts"]), len(p["scenes"])
        p["events"] = [dict(r) for r in db.execute("SELECT * FROM events WHERE project_id=? ORDER BY id DESC LIMIT 100", (key,))]
        p["tasks"] = [dict(r) for r in db.execute("SELECT id,project_id,scene_id,stage,owner,expires,status,created FROM tasks WHERE project_id=? ORDER BY created DESC", (key,))]
        p["jobs"] = [{**dict(r), "data": json.loads(r["data"])} for r in db.execute("SELECT * FROM jobs WHERE project_id=? ORDER BY created DESC", (key,))]
        p["timeline"] = [{**dict(r), **json.loads(r["data"]), "version": versions.get(r["version_id"])} for r in db.execute("SELECT * FROM timeline WHERE project_id=? ORDER BY ordinal", (key,))]
        return p

    def next_action(self, project, scene_id=None):
        p = self.project(project)
        return self._next(p, scene_id)

    def _next(self, p, scene_id=None):
        if scene_id and not any(s["id"] == scene_id for s in p["scenes"]):
            raise Problem("Scene does not belong to this project.")
        for stage in p["stage_status"]:
            items = [a for a in p["artifacts"] if a["stage"] == stage["id"] and a["kind"] == stage["kind"] and (not scene_id or stage["scope"] == "project" or a["scene_id"] == scene_id)]
            if scene_id and stage["scope"] == "scene":
                complete = any(a["approved_version_id"] and not next(v for v in a["versions"] if v["id"] == a["approved_version_id"])["stale"] for a in items)
            else:
                complete = stage["complete"]
            if complete:
                continue
            waiting = [a for a in items if a["latest"] and a["latest"]["effective_status"] == "in_review"]
            inputs = [a["approved_version_id"] for a in p["artifacts"] if a["approved_version_id"] and STAGES.index(a["stage"]) < STAGES.index(stage["id"]) and (not scene_id or not a["scene_id"] or a["scene_id"] == scene_id) and not next(v for v in a["versions"] if v["id"] == a["approved_version_id"])["stale"]]
            return {"stage": stage["id"], "name": stage["name"], "state": "awaiting_review" if waiting else "ready", "instruction": stage["instruction"], "deliverable": stage["deliverable"], "checks": stage["checks"], "inputs": inputs, "scene_id": scene_id, "needs_scene": stage["scope"] == "scene" and not scene_id, "feedback": [r for a in items for v in a["versions"][:1] for r in v["reviews"]], "review_versions": [a["latest"]["id"] for a in waiting]}
        return {"stage": "complete", "name": "Complete", "state": "complete", "inputs": [], "instruction": "All required stages have approved artifacts."}

    def add_version(self, project, payload, uploaded=None, actor="director", enforce_gate=False):
        kind = payload.get("kind", "notes")
        stage = payload.get("stage", "premise")
        if kind not in KINDS or stage not in STAGES:
            raise Problem("Unknown artifact kind or workflow stage.")
        title = text(payload.get("title", ""), "Artifact title", 160, True)
        content = text(payload.get("content", ""), "Artifact text")
        prompt = text(payload.get("prompt", ""), "Generation prompt", 20000)
        metadata = payload.get("metadata", {})
        if not isinstance(metadata, dict) or len(encode(metadata)) > 100000:
            raise Problem("Metadata must be a JSON object smaller than 100 KB.")
        inputs = payload.get("inputs", [])
        if not isinstance(inputs, list) or len(inputs) > 100 or any(not isinstance(x, str) for x in inputs):
            raise Problem("Inputs must be a list of version IDs.")
        version_id = ident("version")
        with self.db(True) as db:
            p = self._project(db, project)
            scene_id = payload.get("scene_id") or None
            scene = next((s for s in p["scenes"] if s["id"] == scene_id), None)
            if scene_id and not scene:
                raise Problem("Scene belongs to another project.")
            artifact_id = payload.get("artifact_id")
            previous = None
            if artifact_id:
                artifact = self.required(db, "artifacts", artifact_id)
                if artifact["project_id"] != project:
                    raise Problem("Artifact belongs to another project.")
                previous = db.execute("SELECT * FROM versions WHERE artifact_id=? ORDER BY number DESC LIMIT 1", (artifact_id,)).fetchone()
                if not previous or payload.get("expected_version") != previous["id"]:
                    raise Problem("A newer version exists. Refresh before saving your changes.", 409)
                kind, stage, scene_id = artifact["kind"], artifact["stage"], artifact["scene_id"]
                title = artifact["title"]
                scene = next((s for s in p["scenes"] if s["id"] == scene_id), None)
            else:
                artifact_id = ident("artifact")
                db.execute("INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)", (artifact_id, project, scene_id, kind, stage, title, now()))
            if enforce_gate:
                eligible = self._next(p, scene_id)
                if eligible["stage"] != stage or eligible["state"] != "ready":
                    raise Problem(f"The next permitted action is {eligible['name']} ({eligible['state']}).", 409)
                if eligible.get("needs_scene"):
                    raise Problem("Select a scene package for this stage.")
                if set(eligible["inputs"]) - set(inputs):
                    raise Problem("Include the pinned approved inputs from get_next_action.", 409)
                if not payload.get("task_id"):
                    raise Problem("Claim the task before registering agent work.", 409)
            if payload.get("task_id"):
                claim = self._check_claim(db, payload["task_id"], payload.get("task_token"), project)
                if claim["stage"] != stage or claim["scene_id"] != scene_id:
                    raise Problem("The artifact must match the claimed stage and scene.", 409)
            for source in inputs:
                dep = db.execute("SELECT a.project_id,a.id FROM versions v JOIN artifacts a ON a.id=v.artifact_id WHERE v.id=?", (source,)).fetchone()
                if not dep or dep["project_id"] != project or dep["id"] == artifact_id:
                    raise Problem("Input versions must belong to this project and another artifact.")
            files = []
            if previous and payload.get("inherit_files", True):
                files = json.loads(previous["data"]).get("files", [])
            if uploaded:
                files = []
                folder = self.root / "assets" / version_id
                folder.mkdir(parents=True, exist_ok=False)
                for index, item in enumerate(uploaded):
                    filename, source = item
                    suffix = Path(filename).suffix.lower()
                    if suffix not in EXTENSIONS:
                        raise Problem(f"Unsupported file type: {suffix or filename}")
                    safe_name = f"{index:02d}_" + "".join(c for c in Path(filename).name if c.isalnum() or c in " ._-()")[:160]
                    dest = folder / safe_name
                    if isinstance(source, bytes):
                        dest.write_bytes(source)
                    else:
                        shutil.copyfile(source, dest)
                    size = dest.stat().st_size
                    if size > 200 * 1024 * 1024:
                        raise Problem("Each file must be 200 MB or smaller.")
                    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
                    if suffix in (".md", ".srt", ".csv", ".txt"):
                        mime = "text/plain"
                    files.append({"name": Path(filename).name, "path": dest.relative_to(self.root).as_posix(), "mime": mime, "size": size, "sha256": hashlib.sha256(dest.read_bytes()).hexdigest()})
            if not (files or content or prompt):
                raise Problem("Add a file, script, notes or prompt before saving.")
            version = {"content": content, "prompt": prompt, "metadata": metadata, "inputs": list(dict.fromkeys(inputs)), "files": files, "author": actor, "submitted": False, "scene_id": scene_id, "scene_revision": scene["revision"] if scene else None, "direction_hash": direction_hash(p), "task_id": payload.get("task_id")}
            version["hash"] = hashlib.sha256(encode(version).encode()).hexdigest()
            number = previous["number"] + 1 if previous else 1
            db.execute("INSERT INTO versions VALUES(?,?,?,?,?)", (version_id, artifact_id, number, encode(version), now()))
            self.event(db, project, "artifact", f"Saved {title} v{number}", actor)
        return {"artifact_id": artifact_id, "version_id": version_id, "number": number}

    def get_version(self, version_id):
        with self.db() as db:
            v = self.required(db, "versions", version_id)
            a = self.required(db, "artifacts", v["artifact_id"])
        p = self.project(a["project_id"])
        artifact = next(x for x in p["artifacts"] if x["id"] == a["id"])
        return {"project_id": a["project_id"], "artifact": {k: v for k, v in artifact.items() if k not in ("versions", "latest")}, "version": next(v for v in artifact["versions"] if v["id"] == version_id)}

    def file_path(self, version_id, index):
        record = self.get_version(version_id)
        files = record["version"]["files"]
        if not isinstance(index, int) or not 0 <= index < len(files):
            raise Problem("File not found.", 404)
        info = files[index]
        path = (self.root / info["path"]).resolve()
        if not path.is_relative_to(self.root / "assets") or not path.is_file():
            raise Problem("Registered file is missing.", 404)
        return path, info

    def checks(self, version_id):
        record = self.get_version(version_id)
        v, a = record["version"], record["artifact"]
        issues, passed = [], []
        p = self.project(record["project_id"])
        stage = next(s for s in WORKFLOW["stages"] if s["id"] == a["stage"])
        if a["kind"] == stage["kind"]:
            if stage["scope"] == "scene" and not a["scene_id"]:
                issues.append("This stage needs a scene package.")
            if stage["scope"] == "project" and a["scene_id"]:
                issues.append("This deliverable must be scoped to the whole project.")
            if not p["settings"].get("demo"):
                required = [x["approved_version_id"] for x in p["artifacts"] if x["approved_version_id"] and STAGES.index(x["stage"]) < STAGES.index(a["stage"]) and (not a["scene_id"] or not x["scene_id"] or x["scene_id"] == a["scene_id"])]
                if set(required) - set(v["inputs"]):
                    issues.append("Pin the current approved upstream versions before requesting approval.")
        if v["stale"]:
            issues.append("Approved inputs or scene direction changed. Create a reviewed replacement version.")
        for index, file in enumerate(v["files"]):
            path, _ = self.file_path(version_id, index)
            if hashlib.sha256(path.read_bytes()).hexdigest() != file["sha256"]:
                issues.append(f"File integrity changed: {file['name']}")
        if v["files"]:
            passed.append("Registered file hashes verified")
        images = [f for f in v["files"] if f["mime"].startswith("image/")]
        media = [f for f in v["files"] if f["mime"].startswith(("video/", "audio/"))]
        if a["kind"] == "comic" and len(images) != 10:
            issues.append("The comic package needs exactly 10 page images.")
        if a["kind"] == "storyboard" and not images:
            issues.append("Add the storyboard images.")
        if a["kind"] == "storyboard" and not v["metadata"].get("reference_map"):
            issues.append("Explain character IDs and the ordered reference mapping in metadata.reference_map.")
        if a["kind"] in ("audio", "previs", "video", "edit") and not media:
            issues.append("Add playable media to this package.")
        if a["kind"] in ("previs", "video", "edit") and not any(f["mime"].startswith("video/") for f in media):
            issues.append("This stage requires a playable video.")
        if a["kind"] == "previs" and not any(f["name"].lower().endswith(".blend") for f in v["files"]):
            issues.append("Attach the editable Blender scene (.blend).")
        if a["kind"] in ("premise", "script") and not v["content"]:
            issues.append("Add the readable story or script text.")
        timing = v["metadata"].get("timing_passed")
        if a["kind"] == "audio" and timing is False:
            issues.append("Audio timing check failed.")
        if a["kind"] == "audio" and timing is not True:
            issues.append("Include a passing timing report (metadata.timing_passed).")
        if timing is True:
            passed.append("Audio tool reported passing timing checks")
        if a["kind"] in ("video", "previs", "audio") and not v["metadata"].get("duration"):
            issues.append("Record the measured media duration in metadata.duration.")
        if v["metadata"].get("duration"):
            numeric(v["metadata"]["duration"], "Measured duration", .001, 86400)
        if media and a["kind"] in ("audio", "previs", "video", "edit"):
            from .media import inspect_media
            index = next(i for i, f in enumerate(v["files"]) if f["mime"].startswith(("audio/", "video/")))
            try:
                measured = inspect_media(self.file_path(version_id, index)[0])
                actual = measured.get("duration")
                if not actual:
                    issues.append("Media duration could not be measured; install ffprobe for video imports.")
                elif abs(actual - v["metadata"].get("duration", actual)) > 1/30:
                    issues.append("Recorded duration does not match the media file.")
                scene = next((s for s in p["scenes"] if s["id"] == a["scene_id"]), None)
                if actual and scene and a["kind"] in ("audio", "previs", "video") and abs(actual-scene["duration"]) > 1/30:
                    issues.append("Media duration does not match the scene package.")
            except (ValueError, OSError, KeyError) as error:
                issues.append(f"Could not inspect media: {error}")
        if not issues:
            passed.append("Artifact structure is ready for human review")
        return {"passed": not issues, "checks": passed, "issues": issues, "human_review_required": True}

    def submit(self, version_id, actor="agent"):
        record = self.get_version(version_id)
        checks = self.checks(version_id)
        if not checks["passed"]:
            raise Problem(" ".join(checks["issues"]), 409)
        with self.db(True) as db:
            row = self.required(db, "versions", version_id)
            value = json.loads(row["data"])
            value["submitted"] = True
            db.execute("UPDATE versions SET data=? WHERE id=?", (encode(value), version_id))
            self.event(db, record["project_id"], "review", f"Submitted {record['artifact']['title']} v{row['number']} for review", actor)
        return checks

    def review(self, version_id, decision, note="", anchor=None):
        if decision not in ("approved", "changes_requested", "comment"):
            raise Problem("Unknown review decision.")
        note = text(note, "Feedback", 10000, decision in ("changes_requested", "comment"))
        record = self.get_version(version_id)
        if decision == "approved":
            checks = self.checks(version_id)
            if not checks["passed"]:
                raise Problem(" ".join(checks["issues"]), 409)
            p = self.project(record["project_id"])
            if not p["settings"].get("demo"):
                eligible = self._next(p, record["artifact"]["scene_id"])
                if STAGES.index(record["artifact"]["stage"]) > (STAGES.index(eligible["stage"]) if eligible["stage"] in STAGES else 8):
                    raise Problem(f"Approve the {eligible['name']} stage first.", 409)
        anchor = anchor or {}
        if not isinstance(anchor, dict) or len(encode(anchor)) > 2000:
            raise Problem("Invalid feedback anchor.")
        if anchor.get("seconds") is not None:
            numeric(anchor["seconds"], "Timecode", 0, 86400)
        with self.db(True) as db:
            if decision == "approved":
                current = self._project(db, record["project_id"])
                current_artifact = next(a for a in current["artifacts"] if a["id"] == record["artifact"]["id"])
                current_version = next(v for v in current_artifact["versions"] if v["id"] == version_id)
                if current_version["stale"]:
                    raise Problem("Inputs changed while reviewing. Refresh this package.", 409)
                if not current["settings"].get("demo"):
                    eligible = self._next(current, current_artifact["scene_id"])
                    if STAGES.index(current_artifact["stage"]) > (STAGES.index(eligible["stage"]) if eligible["stage"] in STAGES else 8):
                        raise Problem(f"Approve {eligible['name']} first.", 409)
            db.execute("INSERT INTO reviews VALUES(?,?,?,?,?,?)", (ident("review"), version_id, decision, note, encode(anchor), now()))
            self.event(db, record["project_id"], "decision", f"{decision.replace('_',' ').capitalize()}: {record['artifact']['title']} v{record['version']['number']}")
        return {"decision": decision, "version_id": version_id}

    def claim(self, project, owner, scene_id=None, seconds=900):
        owner = text(owner, "Agent name", 100, True)
        numeric(seconds, "Lease seconds", 30, 3600)
        with self.db(True) as db:
            p = self._project(db, project)
            action = self._next(p, scene_id)
            if action["state"] != "ready" or action.get("needs_scene"):
                raise Problem("This work is awaiting review, complete, or needs a scene selection.", 409)
            if next(s for s in WORKFLOW["stages"] if s["id"] == action["stage"])["scope"] == "project":
                scene_id = None
            busy = db.execute("SELECT owner FROM tasks WHERE project_id=? AND COALESCE(scene_id,'')=? AND stage=? AND status='claimed' AND expires>?", (project, scene_id or "", action["stage"], time.time())).fetchone()
            if busy:
                raise Problem(f"This task is already claimed by {busy['owner']}.", 409)
            key, token = ident("task"), uuid.uuid4().hex
            db.execute("INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?,?)", (key, project, scene_id, action["stage"], owner, token, time.time()+seconds, "claimed", encode(action["inputs"]), now()))
            scene = next((s for s in p["scenes"] if s["id"] == scene_id), None)
            context = {"direction_hash": direction_hash(p), "scene_revision": scene["revision"] if scene else None}
            db.execute("INSERT INTO task_context VALUES(?,?)", (key, encode(context)))
            self.event(db, project, "agent", f"{owner} claimed {action['name']}", owner)
        return {"task_id": key, "token": token, "expires_in": seconds, "action": action}

    def _check_claim(self, db, key, token, project=None):
        claim = self.required(db, "tasks", key)
        if claim["token"] != token or claim["expires"] <= time.time() or claim["status"] != "claimed" or (project and claim["project_id"] != project):
            raise Problem("Task lease is invalid or expired. Claim the task again.", 409)
        p = self._project(db, claim["project_id"])
        row = db.execute("SELECT data FROM task_context WHERE task_id=?", (key,)).fetchone()
        context = json.loads(row[0]) if row else {}
        scene = next((s for s in p["scenes"] if s["id"] == claim["scene_id"]), None)
        if context.get("direction_hash") != direction_hash(p) or context.get("scene_revision") != (scene["revision"] if scene else None):
            raise Problem("Creative direction changed. Release this task and claim it again.", 409)
        action = self._next(p, claim["scene_id"])
        if action["stage"] != claim["stage"] or set(action.get("inputs", [])) != set(json.loads(claim["inputs"])):
            raise Problem("Task inputs changed. Refresh and claim a new task.", 409)
        return claim

    def finish_claim(self, key, token, release=False):
        with self.db(True) as db:
            row = self.required(db, "tasks", key)
            if row["token"] != token or row["status"] != "claimed" or row["expires"] <= time.time():
                raise Problem("Task lease is invalid.", 409)
            if not release:
                delivered = [json.loads(v[0]) for v in db.execute("SELECT data FROM versions")]
                if not any(v.get("task_id") == key and v.get("submitted") for v in delivered):
                    raise Problem("Submit a version from this task before completing the handoff.", 409)
            db.execute("UPDATE tasks SET status=? WHERE id=?", ("released" if release else "completed", key))
            self.event(db, row["project_id"], "agent", f"{row['owner']} {'released' if release else 'completed'} {row['stage']}", row["owner"])
        return {"status": "released" if release else "completed"}

    def heartbeat(self, key, token):
        with self.db(True) as db:
            self._check_claim(db, key, token)
            db.execute("UPDATE tasks SET expires=? WHERE id=?", (time.time()+900, key))
        return {"expires_in": 900}

    def save_timeline(self, project, entries, expected_revision=None):
        if not isinstance(entries, list) or len(entries) > 1000:
            raise Problem("Invalid timeline.")
        checked = []
        for item in entries:
            record = self.get_version(item["version_id"])
            v = record["version"]
            if record["project_id"] != project:
                raise Problem("Timeline media belongs to another project.")
            index = item.get("file_index", 0)
            path, info = self.file_path(v["id"], index)
            if not info["mime"].startswith(("video/", "audio/")):
                raise Problem("Choose a playable audio or video file.")
            from .media import inspect_media
            duration = inspect_media(path).get("duration")
            if not duration:
                raise Problem("Record the measured media duration before editing.")
            start = numeric(item.get("in", 0), "In point", 0, duration)
            end = numeric(item.get("out", duration), "Out point", 0, duration)
            if start >= end:
                raise Problem("Out point must follow in point.")
            checked.append({"version_id": v["id"], "file_index": index, "in": start, "out": end, "label": text(item.get("label", record["artifact"]["title"]), "Clip label", 160)})
        with self.db(True) as db:
            current = self.required(db, "projects", project)
            if expected_revision is not None and expected_revision != current["revision"]:
                raise Problem("This project or timeline changed. Refresh before saving.", 409)
            db.execute("DELETE FROM timeline WHERE project_id=?", (project,))
            for ordinal, item in enumerate(checked):
                db.execute("INSERT INTO timeline VALUES(?,?,?,?,?)", (ident("cut"), project, item["version_id"], ordinal, encode(item)))
            self.event(db, project, "edit", f"Saved rough cut with {len(checked)} clips")
            db.execute("UPDATE projects SET revision=revision+1 WHERE id=?", (project,))
        return checked

    def create_job(self, project, kind, scene_id=None, data=None):
        key = ident("job")
        with self.db(True) as db:
            self.required(db, "projects", project)
            db.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?)", (key, project, scene_id, kind, "queued", encode(data or {}), now(), now()))
            self.event(db, project, "job", f"Queued {kind}")
        return key

    def update_job(self, key, status, data):
        with self.db(True) as db:
            row = self.required(db, "jobs", key)
            db.execute("UPDATE jobs SET status=?,data=?,updated=? WHERE id=?", (status, encode(data), now(), key))
            self.event(db, row["project_id"], "job", f"{row['kind']}: {status}", "worker")

    def export_project(self, project):
        p = self.project(project)
        directory = self.root / "exports"
        directory.mkdir(exist_ok=True)
        destination = directory / f"{project}-{uuid.uuid4().hex[:8]}.zip"
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("project.json", encode(p))
            archive.writestr("workflow.json", encode(WORKFLOW))
            archive.writestr("timeline.json", encode(p["timeline"]))
            archive.writestr("README.txt", "Director Studio project export. project.json includes version hashes, prompts, reviews and dependency IDs. Files under assets/ are immutable sources. timeline.json records editable in/out points. Secrets and API credentials are not included.\n")
            included = set()
            for a in p["artifacts"]:
                for v in a["versions"]:
                    archive.writestr(f"prompts/{v['id']}.txt", v["prompt"])
                    for i, file in enumerate(v["files"]):
                        if file["path"] not in included:
                            path, _ = self.file_path(v["id"], i)
                            archive.write(path, file["path"])
                            included.add(file["path"])
        return destination

    def generation_package(self, project, scene_id):
        p = self.project(project)
        scene = next((s for s in p["scenes"] if s["id"] == scene_id), None)
        if not scene:
            raise Problem("Select a scene.")
        selected, missing = {}, []
        for stage in ("audio", "boards", "blender"):
            stage_kind = next(s["kind"] for s in WORKFLOW["stages"] if s["id"] == stage)
            candidates = [a for a in p["artifacts"] if a["stage"] == stage and a["kind"] == stage_kind and a["scene_id"] == scene_id and a["approved_version_id"]]
            versions = [next(v for v in a["versions"] if v["id"] == a["approved_version_id"]) for a in candidates]
            versions = [v for v in versions if not v["stale"]]
            if not versions:
                missing.append(stage)
            else:
                selected[stage] = versions[-1]
        if missing:
            raise Problem("Approve current scene artifacts first: " + ", ".join(missing), 409)
        prompt_version = selected["blender"] if selected["blender"]["prompt"] else selected["boards"]
        if not prompt_version["prompt"]:
            raise Problem("The approved package needs a generation prompt.")
        duration = int(scene["duration"])
        refs = prompt_version["metadata"].get("reference_media", [])
        if not isinstance(refs, list):
            raise Problem("reference_media must be a list.")
        from urllib.parse import urlparse
        video_total = audio_total = 0
        counts = {"reference_video": 0, "reference_audio": 0, "reference_image": 0}
        for ref in refs:
            if not isinstance(ref, dict) or not isinstance(ref.get("url"), str):
                raise Problem("Every reference must be an object with a URL.")
            address = urlparse(ref["url"])
            if ref.get("type") not in counts or address.scheme != "https" or not address.hostname or address.username or address.password:
                raise Problem("Reference media need a supported reference type and HTTPS URL.")
            counts[ref["type"]] += 1
            if ref["type"] in ("reference_video", "reference_audio"):
                length = numeric(ref.get("duration"), "Reference duration", 1, 15)
                video_total += length if ref["type"] == "reference_video" else 0
                audio_total += length if ref["type"] == "reference_audio" else 0
        if video_total > 15 or audio_total > 15 or video_total + duration > 30 or counts["reference_video"] > 5 or counts["reference_audio"] > 5 or counts["reference_image"] > 10:
            raise Problem("Wan reference limits exceeded.")
        return {"model": "wan3.0-video", "input": {"prompt": prompt_version["prompt"], "media": [{"type": r["type"], "url": r["url"]} for r in refs]}, "parameters": {"duration": duration, "ratio": p["settings"]["aspect_ratio"], "resolution": "720P", "audio": True, "prompt_extend": bool(prompt_version["metadata"].get("prompt_extend", False))}, "provenance": {"project_id": project, "scene_id": scene_id, "versions": {k: v["id"] for k,v in selected.items()}, "prompt_version": prompt_version["id"]}, "ready_for_api": bool(refs) and counts["reference_video"] > 0 and counts["reference_audio"] > 0 and counts["reference_image"] > 0, "submission": "Prepared for manual or agent submission; no paid request made."}
