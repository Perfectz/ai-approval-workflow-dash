"""Behavior checks for preserving speech, deliberate overlap and safe package boundaries."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import scratch_audio as scratch
from verify_audio import verify


class TimingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        scratch.write_wave(self.folder / "take.wav", (round(5000 * math.sin(2 * math.pi * 220 * i / scratch.RATE)) for i in range(scratch.RATE)))
        self.source = {
            "schema_version": 1, "sequence_id": "TEST", "title": "Timing test", "revision": "test", "target_duration": 15, "fps": 30,
            "characters": {"A": {"name": "A", "voice": "Test", "color": "#64b5ff"}, "B": {"name": "B", "voice": "Test", "color": "#ffbe76"}},
            "shots": [{"id": "SHOT", "start": 0, "end": 15}], "jobs": [{"id": "JOB", "start": 0, "end": 15}],
            "lines": [{"id": "LINE", "character": "A", "start": 1, "slot_end": 3, "text": "Test recording", "audio_file": "take.wav"}], "actions": []}

    def tearDown(self):
        self.temp.cleanup()

    def render(self):
        source_path = self.folder / "source.json"
        source_path.write_text(json.dumps(self.source), encoding="utf-8")
        with redirect_stdout(io.StringIO()):
            output, report = scratch.render(source_path, self.folder / "outputs")
        verify(output)
        return output, report

    def test_measured_audio_silence_isolation_and_preserved_versions(self):
        first, report = self.render()
        self.assertTrue(report["timing_passed"])
        self.assertEqual(report["lines"][0]["duration"], 1)
        self.assertEqual(report["lines"][0]["end"], 2)
        self.assertEqual(report["actual_duration"], 15)
        second, _ = self.render()
        self.assertNotEqual(first, second)
        self.assertTrue((first / "mix.wav").exists())

    def test_overrun_is_preserved_and_reference_is_withheld(self):
        self.source["lines"][0].update(start=14.5, slot_end=15)
        output, report = self.render()
        self.assertFalse(report["timing_passed"])
        self.assertEqual(report["actual_duration"], 15.5)
        self.assertFalse(list((output / "jobs").glob("*.wav")))

    def test_line_crossing_a_generation_boundary_is_not_sliced(self):
        self.source["target_duration"] = 30
        self.source["shots"][0]["end"] = 30
        self.source["jobs"].append({"id": "JOB_B", "start": 15, "end": 30})
        self.source["lines"][0].update(start=14.5, slot_end=17)
        _, report = self.render()
        self.assertFalse(report["timing_passed"])
        self.assertTrue(any("boundary" in issue for issue in report["issues"]))

    def test_unintentional_overlap_is_flagged_but_deliberate_overlap_can_pass(self):
        other = deepcopy(self.source["lines"][0])
        other.update(id="LINE_B", character="B", start=1.5)
        self.source["lines"].append(other)
        _, report = self.render()
        self.assertFalse(report["timing_passed"])
        for line in self.source["lines"]:
            line["allow_overlap"] = True
        _, report = self.render()
        self.assertTrue(report["timing_passed"])

    def test_unsafe_ids_and_invalid_job_lengths_are_rejected(self):
        self.source["lines"][0]["id"] = "../outside"
        with self.assertRaises(ValueError):
            scratch.validate(self.source)
        self.source["lines"][0]["id"] = "LINE"
        self.source["target_duration"] = 30
        self.source["shots"][0]["end"] = 30
        self.source["jobs"][0]["end"] = 30
        with self.assertRaises(ValueError):
            scratch.validate(self.source)

    def test_script_text_is_data_in_review_page(self):
        self.source["lines"][0]["text"] = '</script><script>alert("injected")</script>'
        output, _ = self.render()
        page = (output / "review.html").read_text(encoding="utf-8")
        self.assertNotIn('</script><script>alert("injected")', page)
        self.assertIn('\\u003c/script>', page)


if __name__ == "__main__":
    unittest.main()
