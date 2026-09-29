import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import wave
import zipfile
from concurrent.futures import ThreadPoolExecutor

from studio.store import Store, Problem
from studio.agent_tools import TOOLS


def wave_bytes(seconds=2):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
        out.writeframes(b"\x10\x00" * int(48000 * seconds))
    return buffer.getvalue()


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name)
        self.project = self.store.create_project({"title": "Test film"})["id"]

    def tearDown(self):
        self.temp.cleanup()

    def artifact(self, kind="premise", stage="premise", **extras):
        return self.store.add_version(self.project, {"title": kind, "kind": kind, "stage": stage, "content": "A coherent test story.", **extras})

    def test_upstream_approval_invalidates_only_dependent_work(self):
        source = self.artifact()
        self.store.review(source["version_id"], "approved")
        child = self.artifact("notes", "comic", inputs=[source["version_id"]])
        independent = self.artifact("notes", "comic")
        updated = self.artifact(artifact_id=source["artifact_id"], expected_version=source["version_id"], content="Revised premise.")
        self.assertFalse(self.store.get_version(child["version_id"])["version"]["stale"])
        self.store.review(updated["version_id"], "approved")
        self.assertTrue(self.store.get_version(child["version_id"])["version"]["stale"])
        self.assertFalse(self.store.get_version(independent["version_id"])["version"]["stale"])
        self.assertEqual(self.store.get_version(source["version_id"])["version"]["content"], "A coherent test story.")

    def test_stale_transitively_propagates(self):
        parent = self.artifact()
        self.store.review(parent["version_id"], "approved")
        child = self.artifact("notes", "comic", inputs=[parent["version_id"]])
        self.store.review(child["version_id"], "approved")
        grandchild = self.artifact("notes", "comic", inputs=[child["version_id"]])
        revised = self.artifact(artifact_id=parent["artifact_id"], expected_version=parent["version_id"])
        self.store.review(revised["version_id"], "approved")
        self.assertTrue(self.store.get_version(grandchild["version_id"])["version"]["stale"])

    def test_gate_blocks_early_script_and_does_not_infer_approval(self):
        script = self.artifact("script", "script")
        with self.assertRaises(Problem):
            self.store.review(script["version_id"], "approved")
        premise = self.artifact()
        self.store.submit(premise["version_id"])
        self.assertEqual(self.store.next_action(self.project)["state"], "awaiting_review")
        self.store.review(premise["version_id"], "changes_requested", "Make the ending clear.")
        self.assertEqual(self.store.next_action(self.project)["state"], "ready")
        self.assertEqual(self.store.next_action(self.project)["feedback"][0]["note"], "Make the ending clear.")

    def test_optimistic_version_conflict(self):
        old = self.artifact()
        self.artifact(artifact_id=old["artifact_id"], expected_version=old["version_id"])
        with self.assertRaises(Problem) as error:
            self.artifact(artifact_id=old["artifact_id"], expected_version=old["version_id"])
        self.assertEqual(error.exception.status, 409)

    def test_project_scoping_rejects_foreign_inputs_and_scenes(self):
        other = self.store.create_project({"title": "Other"})["id"]
        source = self.store.add_version(other, {"title": "Other premise", "kind": "premise", "content": "Other story"})
        scene = self.store.save_scene(other, {"title": "Other scene"})
        with self.assertRaises(Problem):
            self.artifact(inputs=[source["version_id"]])
        with self.assertRaises(Problem):
            self.artifact(scene_id=scene)

    def test_concurrent_claims_have_one_winner(self):
        def claim(name):
            try:
                return self.store.claim(self.project, name)
            except Problem:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(claim, ["Agent A", "Agent B"]))
        self.assertEqual(sum(bool(r) for r in results), 1)

    def test_project_task_claim_normalizes_scene_and_cannot_be_duplicated(self):
        scene = self.store.save_scene(self.project, {"title": "Plan"})
        self.store.claim(self.project, "A", scene)
        with self.assertRaises(Problem):
            self.store.claim(self.project, "B")

    def test_creative_edit_invalidates_in_progress_agent_lease(self):
        claim = self.store.claim(self.project, "Writer")
        self.store.update_project(self.project, {"expected_revision": 1, "brief": "A different story"})
        with self.assertRaises(Problem):
            self.store.heartbeat(claim["task_id"], claim["token"])

    def test_timeline_conflict_preserves_existing_edit(self):
        self.store.save_timeline(self.project, [], expected_revision=1)
        with self.assertRaises(Problem):
            self.store.save_timeline(self.project, [], expected_revision=1)

    def test_wan_reference_contract_preserves_order_and_enforces_limits(self):
        refs = [{"type": "reference_image", "url": "https://example.com/cast.png"}, {"type": "reference_video", "url": "https://example.com/previs.mp4", "duration": 15}, {"type": "reference_audio", "url": "https://example.com/timing.wav", "duration": 15}]
        artifacts = []
        for stage, kind in (("audio", "audio"), ("boards", "storyboard"), ("blender", "previs")):
            artifacts.append({"stage": stage, "kind": kind, "scene_id": "s", "approved_version_id": stage, "versions": [{"id": stage, "stale": False, "prompt": "Use Image 1, Video 1 and Audio 1.", "metadata": {"reference_media": refs, "prompt_extend": False}}]})
        fixture = {"scenes": [{"id": "s", "duration": 15}], "artifacts": artifacts, "settings": {"aspect_ratio": "16:9"}}
        with patch.object(self.store, "project", return_value=fixture):
            package = self.store.generation_package(self.project, "s")
            self.assertEqual([r["type"] for r in package["input"]["media"]], [r["type"] for r in refs])
            self.assertEqual(package["parameters"]["duration"], 15)
            self.assertFalse(package["parameters"]["prompt_extend"])
            refs[1]["duration"] = 15.01
            with self.assertRaises(Problem):
                self.store.generation_package(self.project, "s")
            refs[1]["duration"] = 15
            refs.append({"type": "reference_video", "url": "https://example.com/second.mp4", "duration": 1})
            with self.assertRaises(Problem):
                self.store.generation_package(self.project, "s")

    def test_agent_cannot_disguise_later_stage_as_current_stage(self):
        script = self.artifact("script", "script")
        claim = self.store.claim(self.project, "Agent")
        with self.assertRaises(Problem):
            self.store.add_version(self.project, {"title": "Premise", "stage": "premise", "kind": "premise", "content": "Bypass attempt", "artifact_id": script["artifact_id"], "expected_version": script["version_id"], "task_id": claim["task_id"], "task_token": claim["token"]}, enforce_gate=True)

    def test_claim_cannot_complete_without_submission_and_expired_token_fails(self):
        claim = self.store.claim(self.project, "Agent")
        with self.assertRaises(Problem):
            self.store.finish_claim(claim["task_id"], claim["token"])
        with self.store.db(True) as db:
            db.execute("UPDATE tasks SET expires=? WHERE id=?", (time.time()-1, claim["task_id"]))
        with self.assertRaises(Problem):
            self.store.heartbeat(claim["task_id"], claim["token"])

    def test_scene_and_creative_direction_changes_stale_versions(self):
        scene = self.store.save_scene(self.project, {"title": "Opening"})
        result = self.artifact("notes", "audio", scene_id=scene)
        self.store.save_scene(self.project, {"title": "Opening revised", "expected_revision": 1}, scene)
        self.assertTrue(self.store.get_version(result["version_id"])["version"]["stale"])
        premise = self.artifact()
        self.store.update_project(self.project, {"expected_revision": 1, "budget": 50})
        self.assertFalse(self.store.get_version(premise["version_id"])["version"]["stale"])
        self.store.update_project(self.project, {"expected_revision": 2, "creative_locks": "A different protagonist."})
        self.assertTrue(self.store.get_version(premise["version_id"])["version"]["stale"])

    def test_files_are_copied_and_hash_change_blocks_review(self):
        original = Path(self.temp.name) / "source.txt"
        original.write_text("original", encoding="utf-8")
        result = self.store.add_version(self.project, {"title": "source", "content": "Source"}, [(original.name, original)])
        path, _ = self.store.file_path(result["version_id"], 0)
        original.write_text("changed", encoding="utf-8")
        self.assertEqual(path.read_text(), "original")
        path.write_text("corrupted", encoding="utf-8")
        self.assertFalse(self.store.checks(result["version_id"])["passed"])
        with self.assertRaises(Problem):
            self.store.file_path(result["version_id"], -1)

    def test_timeline_ranges_and_export_keep_prompts_and_reviews(self):
        result = self.store.add_version(self.project, {"title": "Take", "kind": "audio", "stage": "audio", "prompt": "Exact prompt", "metadata": {"duration": 2}}, [("take.wav", wave_bytes())])
        self.store.save_timeline(self.project, [{"version_id": result["version_id"], "in": .25, "out": 1.75}])
        with self.assertRaises(Problem):
            self.store.save_timeline(self.project, [{"version_id": result["version_id"], "in": 0, "out": 3}])
        self.assertEqual(len(self.store.project(self.project)["timeline"]), 1)
        self.store.review(result["version_id"], "comment", "Listen to the pause.", {"seconds": .5})
        with zipfile.ZipFile(self.store.export_project(self.project)) as archive:
            self.assertEqual(archive.read(f"prompts/{result['version_id']}.txt").decode(), "Exact prompt")
            exported = json.loads(archive.read("project.json"))
            self.assertEqual(exported["artifacts"][0]["versions"][0]["reviews"][0]["anchor"]["seconds"], .5)
            self.assertTrue(any(n.startswith("assets/") for n in archive.namelist()))

    def test_comic_needs_ten_pages_and_agent_tools_have_no_approve(self):
        comic = self.artifact("comic", "comic")
        self.assertFalse(self.store.checks(comic["version_id"])["passed"])
        self.assertFalse(any("approve" in name or "review_decision" in name for name in TOOLS))

    def test_scene_duration_rejects_fractional_or_long_packages(self):
        for duration in (1, 15.1, 2.5, float("nan"), True):
            with self.assertRaises(Problem):
                self.store.save_scene(self.project, {"title": "bad", "duration": duration})


class ApiTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from studio import app as application
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name)
        self.replace = patch.object(application, "store", self.store)
        self.replace.start()
        self.env = patch.dict(os.environ, {"DIRECTOR_NO_SEED": "1"})
        self.env.start()
        self.client = TestClient(application.app)
        self.client.__enter__()
        self.headers = {"X-Director-Token": self.client.get("/api/session").json()["token"]}

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.replace.stop()
        self.env.stop()
        self.temp.cleanup()

    def test_mutations_need_director_session_and_cross_origin_rejected(self):
        self.assertEqual(self.client.post("/api/projects", json={"title": "Denied"}).status_code, 403)
        response = self.client.post("/api/projects", json={"title": "Denied"}, headers={**self.headers, "Origin": "https://example.com"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.get("/api/session", headers={"Host": "attacker.example"}).status_code, 403)

    def test_upload_measures_audio_and_range_playback(self):
        project = self.client.post("/api/projects", json={"title": "Audio import", "demo": True}, headers=self.headers).json()
        self.assertFalse(project["settings"]["demo"])
        response = self.client.post(f"/api/projects/{project['id']}/artifacts", data={"payload": json.dumps({"title": "Sound", "kind": "audio", "stage": "audio"})}, files={"files": ("sample.wav", wave_bytes(), "audio/wav")}, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        version = response.json()["version_id"]
        self.assertEqual(self.store.get_version(version)["version"]["metadata"]["duration"], 2)
        response = self.client.get(f"/api/media/{version}/0", headers={"Range": "bytes=0-99"})
        self.assertEqual(response.status_code, 206)
        self.assertEqual(len(response.content), 100)
        self.assertTrue(response.headers["content-range"].startswith("bytes 0-99/"))


if __name__ == "__main__":
    unittest.main()
