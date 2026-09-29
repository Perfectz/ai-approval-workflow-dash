import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile

from studio.store import Store, Problem, WORKFLOW
from studio.agent_tools import TOOLS


class SpriteWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = Store(self.directory.name)
        self.project = self.store.create_project({"title": "QA sprites", "workflow_id": "sprite-to-flow"})["id"]
        # Technical fixture only; no creative assets are generated or approved in user records.
        from PIL import Image
        self.image = Path(self.directory.name) / "reference.png"
        Image.new("RGBA", (32, 32), (40, 100, 160, 255)).save(self.image)

    def approved(self, stage, kind, **extras):
        action = self.store.next_action(self.project, extras.get("scene_id"))
        files = extras.pop("files", [])
        value = self.store.add_version(self.project, {"title": stage, "stage": stage, "kind": kind, "content": "Isolated technical test fixture.", "inputs": action["inputs"], **extras}, files)
        self.store.review(value["version_id"], "approved", "QA approval in temporary test records")
        return value

    def ready_for_flow(self, allowance=None):
        self.approved("sprite_brief", "sprite_brief")
        self.approved("sprite_design", "sprite_design", files=[("reference.png", self.image)])
        self.approved("sprite_motion", "sprite_motion")
        scene = self.store.save_scene(self.project, {"title": "idle right", "duration": 8})
        board = self.approved("sprite_boards", "sprite_board", scene_id=scene, prompt="One fixed camera and one complete idle cycle on magenta.", files=[("clean-frame.png", self.image)], metadata={"reference_map": "CHAR_A = clean-frame.png", "flow_references": [{"version_id": "self", "file_index": 0, "role": "first_frame"}], "flow_allowance": allowance or {"max_generations": 2, "max_credits": 20, "outputs_per_generation": 1, "upload_authorized": True}})
        return scene, board

    def test_modes_are_pinned_and_cross_mode_stages_rejected(self):
        p = self.store.project(self.project)
        self.assertEqual(p["workflow_id"], "sprite-to-flow")
        self.assertEqual(self.store.next_action(self.project)["stage"], "sprite_brief")
        film = self.store.create_project({"title": "Existing film"})
        self.assertEqual(film["settings"]["workflow_id"], WORKFLOW["id"])
        self.assertEqual(self.store.next_action(film["id"])["stage"], "premise")
        with self.assertRaises(Problem):
            self.store.add_version(self.project, {"title": "wrong", "stage": "premise", "kind": "premise", "content": "No."})
        with self.assertRaises(Problem):
            self.store.update_project(self.project, {"expected_revision": 1, "workflow_id": "comic-to-wan"})

    def test_sprite_gate_does_not_advance_on_technical_pass(self):
        claim = self.store.claim(self.project, "sprite agent")
        value = self.store.add_version(self.project, {"title": "brief", "kind": "sprite_brief", "stage": "sprite_brief", "content": "An original game creature with eight idle poses.", "task_id": claim["task_id"], "task_token": claim["token"], "inputs": []}, enforce_gate=True)
        self.store.submit(value["version_id"])
        self.store.finish_claim(claim["task_id"], claim["token"])
        self.assertEqual(self.store.next_action(self.project)["state"], "awaiting_review")
        self.assertFalse(any("approve" in name for name in TOOLS))

    def test_omni_duration_contract_does_not_change_film_packages(self):
        for value in (2, 3, 5, 15, 8.5):
            with self.assertRaises(Problem):
                self.store.save_scene(self.project, {"title": "bad", "duration": value})
        scene = self.store.save_scene(self.project, {"title": "good", "duration": 10, "frame_count": 12})
        self.assertEqual(self.store.project(self.project)["scenes"][0]["frame_count"], 12)
        film = self.store.create_project({"title": "film"})["id"]
        self.store.save_scene(film, {"title": "15s", "duration": 15})

    def test_browser_package_uses_approved_local_refs_and_no_api(self):
        scene, board = self.ready_for_flow()
        package = self.store.generation_package(self.project, scene)
        self.assertTrue(package["ready_for_browser"])
        self.assertFalse(package["ready_for_api"])
        self.assertEqual(package["mode"], "browser_ui")
        self.assertEqual(package["provenance"]["board_version_id"], board["version_id"])
        self.assertEqual(package["references"][0]["version_id"], board["version_id"])
        self.assertTrue(Path(package["references"][0]["local_path"]).is_file())
        self.assertNotIn("api_key", json.dumps(package))

    def test_flow_reservation_blocks_uncertain_retry_and_enforces_caps(self):
        scene, _ = self.ready_for_flow()
        claim = self.store.claim(self.project, "browser sprite agent", scene)
        attempt = self.store.reserve_flow_attempt(self.project, scene, claim["task_id"], claim["token"], "Omni Flash", 12)
        self.store.record_flow_result(attempt["attempt_id"], claim["task_id"], claim["token"], "unknown", "Generate clicked; UI response was interrupted")
        with self.assertRaisesRegex(Problem, "unresolved"):
            self.store.reserve_flow_attempt(self.project, scene, claim["task_id"], claim["token"], "Omni Flash", 1)
        self.store.record_flow_result(attempt["attempt_id"], claim["task_id"], claim["token"], "failed", "Visible failure on the same existing generation")
        with self.assertRaisesRegex(Problem, "allowance"):
            self.store.reserve_flow_attempt(self.project, scene, claim["task_id"], claim["token"], "Omni Flash", 9)
        second = self.store.reserve_flow_attempt(self.project, scene, claim["task_id"], claim["token"], "Omni Flash", 8)
        self.store.record_flow_result(second["attempt_id"], claim["task_id"], claim["token"], "failed", "Second permitted attempt visibly failed")
        with self.assertRaisesRegex(Problem, "allowance"):
            self.store.reserve_flow_attempt(self.project, scene, claim["task_id"], claim["token"], "Omni Flash", 0)

    def test_no_upload_permission_means_no_flow_reservation(self):
        scene, _ = self.ready_for_flow({"max_generations": 1, "max_credits": 20, "outputs_per_generation": 1, "upload_authorized": False})
        package = self.store.flow_package(self.project, scene)
        self.assertFalse(package["ready_for_browser"])
        claim = self.store.claim(self.project, "browser agent", scene)
        with self.assertRaises(Problem):
            self.store.reserve_flow_attempt(self.project, scene, claim["task_id"], claim["token"], "Omni Flash", 1)

    def test_animation_edit_invalidates_prepared_browser_inputs(self):
        scene, board = self.ready_for_flow()
        claim = self.store.claim(self.project, "browser agent", scene)
        self.store.save_scene(self.project, {"title": "idle left", "expected_revision": 1, "direction": "left"}, scene)
        self.assertTrue(self.store.get_version(board["version_id"])["version"]["stale"])
        with self.assertRaises(Problem):
            self.store.flow_package(self.project, scene)
        with self.assertRaises(Problem):
            self.store.heartbeat(claim["task_id"], claim["token"])

    def test_export_contains_actual_mode_not_film_default(self):
        with zipfile.ZipFile(self.store.export_project(self.project)) as archive:
            self.assertEqual(json.loads(archive.read("workflow.json"))["id"], "sprite-to-flow")

    def test_project_sprite_defaults_are_used_for_new_animations(self):
        project = self.store.create_project({"title": "64px Unity assets", "workflow_id": "sprite-to-flow", "target_engine": "Unity", "cell_width": 64, "cell_height": 96})
        scene = self.store.save_scene(project["id"], {"title": "jump", "action": "jump"})
        saved = self.store.project(project["id"])["scenes"][0]
        self.assertEqual(project["settings"]["target_engine"], "Unity")
        self.assertEqual((saved["cell_width"], saved["cell_height"]), (64, 96))
        self.assertFalse(saved["loop"])
        with self.assertRaisesRegex(Problem, "whole number"):
            self.store.save_scene(project["id"], {"title": "fractional padding", "padding": 2.5})

    def test_flow_reference_integrity_is_checked_before_handoff(self):
        scene, board = self.ready_for_flow()
        path, _ = self.store.file_path(board["version_id"], 0)
        path.write_bytes(b"altered after approval")
        with self.assertRaisesRegex(Problem, "changed on disk"):
            self.store.flow_package(self.project, scene)

    def test_flow_attempt_can_be_reconciled_after_original_lease_expires(self):
        scene, _ = self.ready_for_flow()
        original = self.store.claim(self.project, "first browser", scene)
        attempt = self.store.reserve_flow_attempt(self.project, scene, original["task_id"], original["token"], "Omni Flash", 12)
        self.store.record_flow_result(attempt["attempt_id"], original["task_id"], original["token"], "unknown", "Interrupted after clicking Generate")
        with self.store.db(True) as db:
            db.execute("UPDATE tasks SET expires=0 WHERE id=?", (original["task_id"],))
        recovery = self.store.claim(self.project, "recovery browser", scene)
        self.store.record_flow_result(attempt["attempt_id"], recovery["task_id"], recovery["token"], "failed", "Existing result visibly failed; no new click")
        with self.store.db() as db:
            row = dict(db.execute("SELECT * FROM jobs WHERE id=?", (attempt["attempt_id"],)).fetchone())
        data = json.loads(row["data"])
        self.assertEqual(row["status"], "failed")
        self.assertEqual(data["task_id"], original["task_id"])
        self.assertEqual(data["reconciled_by_task_id"], recovery["task_id"])
        self.assertEqual(data["reserved_credits"], 12)

    def test_concurrent_local_pack_jobs_have_one_winner(self):
        scene = self.store.save_scene(self.project, {"title": "idle"})
        def queue(_):
            try:
                return self.store.create_job(self.project, "sprite_pack", scene)
            except Problem:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(queue, range(2)))
        self.assertEqual(sum(value is not None for value in results), 1)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg and ffprobe not installed")
    def test_approved_clip_packs_and_exports_a_portable_atlas(self):
        scene, _ = self.ready_for_flow()
        claim = self.store.claim(self.project, "technical fixture browser", scene)
        attempt = self.store.reserve_flow_attempt(self.project, scene, claim["task_id"], claim["token"], "Gemini Omni Flash 1.1", 0)
        self.store.record_flow_result(attempt["attempt_id"], claim["task_id"], claim["token"], "downloaded", "Simulated receipt in temporary technical fixture; no provider execution")
        source = Path(self.directory.name) / "technical-fixture.mp4"
        subprocess.run([shutil.which("ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin", "-f", "lavfi", "-i", "color=c=magenta:s=160x90:r=8:d=8", "-vf", "drawbox=x=60:y=15:w=40:h=60:color=blue:t=fill", "-c:v", "libx264rgb", "-crf", "0", str(source)], check=True)
        action = self.store.next_action(self.project, scene)
        clip = self.store.add_version(self.project, {"title": "Technical fixture only", "kind": "sprite_video", "stage": "sprite_flow", "scene_id": scene, "inputs": action["inputs"], "prompt": "Technical fixture prompt", "task_id": claim["task_id"], "task_token": claim["token"], "metadata": {"flow": {"provider": "Google Flow", "execution": "browser_ui", "selected_model": "Gemini Omni Flash 1.1", "attempt_id": attempt["attempt_id"], "settings": {"duration": 8, "aspect_ratio": "16:9", "outputs": 1}, "evidence": "Simulated receipt in temporary technical fixture"}}}, [(source.name, source)], enforce_gate=True)
        self.store.submit(clip["version_id"])
        self.store.finish_claim(claim["task_id"], claim["token"])
        self.store.review(clip["version_id"], "approved", "Temporary technical test only")
        extraction = self.store.claim(self.project, "local processor", scene)
        packed = self.store.pack_sprite_artifact(self.project, scene, clip["version_id"], {}, extraction["task_id"], extraction["token"])
        self.assertTrue(packed["qc"]["passed"])
        self.assertTrue(self.store.checks(packed["version_id"])["passed"])
        self.assertEqual(self.store.get_version(packed["version_id"])["version"]["status"], "draft")
        self.assertEqual(self.store.get_version(packed["version_id"])["version"]["metadata"]["reference_map"], "CHAR_A = clean-frame.png")
        with zipfile.ZipFile(self.store.export_project(self.project)) as archive:
            prefix = f"sprites/{scene}/{packed['version_id']}/"
            atlas = json.loads(archive.read(prefix + "atlas.json"))
            self.assertTrue(atlas["animation"]["loop"])
            self.assertEqual(archive.read(prefix + "source.mp4"), source.read_bytes())
            self.assertIn(prefix + atlas["meta"]["image"], archive.namelist())
            self.assertTrue(all(prefix + f["file"] in archive.namelist() for f in atlas["frames"]))
        # A malformed externally supplied atlas must fail review rather than crash.
        record = self.store.get_version(packed["version_id"])
        files = [(f["name"], self.store.file_path(packed["version_id"], i)[0]) for i, f in enumerate(record["version"]["files"])]
        broken_atlas = Path(self.directory.name) / "bad-atlas.json"
        atlas["frames"][0] = "invalid rectangle"
        broken_atlas.write_text(json.dumps(atlas))
        files[2] = ("atlas.json", broken_atlas)
        bad = self.store.add_version(self.project, {"artifact_id": packed["artifact_id"], "expected_version": packed["version_id"], "title": "bad external atlas", "kind": "sprite_sheet", "stage": "sprite_sheet", "scene_id": scene, "inputs": record["version"]["inputs"], "content": "QA invalid atlas", "metadata": record["version"]["metadata"]}, files)
        checks = self.store.checks(bad["version_id"])
        self.assertFalse(checks["passed"])
        self.assertIn("Atlas frames must be a list of frame objects", " ".join(checks["issues"]))
        invalid_qc = {**record["version"]["metadata"], "sprite": {**record["version"]["metadata"]["sprite"], "qc": "invalid report"}}
        files[2] = ("atlas.json", self.store.file_path(packed["version_id"], 2)[0])
        bad_qc = self.store.add_version(self.project, {"artifact_id": packed["artifact_id"], "expected_version": bad["version_id"], "title": "bad QC", "kind": "sprite_sheet", "stage": "sprite_sheet", "scene_id": scene, "inputs": record["version"]["inputs"], "content": "QA invalid QC", "metadata": invalid_qc}, files)
        self.assertIn("Include passing local sprite-processing QC.", self.store.checks(bad_qc["version_id"])["issues"])


if __name__ == "__main__":
    unittest.main()
