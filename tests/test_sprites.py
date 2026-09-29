"""Behavior checks using authored pixels and a tiny local lossless video."""
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw

from studio.sprites import _pack_images, pack_video, validate_settings


class SpriteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.settings = {"start_seconds": 0, "end_seconds": 1, "frame_count": 2,
                         "cell_width": 32, "cell_height": 32, "columns": 2,
                         "sprite_fps": 8, "padding": 2, "key_tolerance": 0}

    def tearDown(self):
        self.temp.cleanup()

    def write_frame(self, name, box, *, color=(0, 220, 60), background="#FF00FF"):
        frame = Image.new("RGB", (40, 40), background)
        if box:
            ImageDraw.Draw(frame).rectangle(box, fill=color)
        path = self.folder / name
        frame.save(path)
        return path

    def pack_images(self, paths, settings=None):
        output = self.folder / "atlas"
        output.mkdir()
        config = validate_settings(settings or self.settings)
        _pack_images(paths, output, config, [0, 0.5], {"sha256": "synthetic"})
        return output, json.loads((output / "atlas.json").read_text()), json.loads((output / "qc.json").read_text())

    def test_shared_transform_preserves_relative_pose_size_and_transparency(self):
        first = self.write_frame("first.png", (10, 10, 19, 29))
        second = self.write_frame("second.png", (10, 20, 14, 29))
        output, atlas, _ = self.pack_images([first, second])
        a, b = [Image.open(output / "frames" / f"frame_{i:04d}.png").convert("RGBA") for i in (1, 2)]
        box_a, box_b = a.getchannel("A").getbbox(), b.getchannel("A").getbbox()
        self.assertGreater(box_a[2] - box_a[0], (box_b[2] - box_b[0]) * 1.5)
        self.assertEqual(box_a[3], box_b[3])
        self.assertEqual(a.getpixel((0, 0))[3], 0)
        self.assertEqual(atlas["frames"][0]["pivot_pixels"], atlas["frames"][1]["pivot_pixels"])
        self.assertEqual(atlas["sheet"]["width"], 64)
        self.assertTrue(atlas["transform"]["shared_across_frames"])
        # Nearest-neighbor sampling adds no blended sprite colors.
        self.assertEqual({pixel[:3] for pixel in a.getdata() if pixel[3]}, {(0, 220, 60)})
        with Image.open(output / "animation.gif") as preview:
            self.assertNotIn("loop", preview.info)

    def test_common_alignment_preserves_vertical_motion_instead_of_refitting(self):
        first = self.write_frame("ground.png", (10, 10, 19, 29))
        second = self.write_frame("jump.png", (10, 4, 19, 23))
        output, _, _ = self.pack_images([first, second])
        with Image.open(output / "frames/frame_0001.png") as a, Image.open(output / "frames/frame_0002.png") as b:
            self.assertGreater(a.getchannel("A").getbbox()[3], b.getchannel("A").getbbox()[3])

    def test_existing_alpha_is_preserved_without_a_background_key(self):
        image = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
        ImageDraw.Draw(image).rectangle((10, 10, 19, 29), fill=(255, 0, 255, 128))
        path = self.folder / "transparent.png"
        image.save(path)
        output, _, report = self.pack_images([path, path], self.settings | {"background_key": None})
        with Image.open(output / "frames/frame_0001.png") as frame:
            self.assertEqual({pixel[3] for pixel in frame.getdata()}, {0, 128})
            self.assertIn((255, 0, 255, 128), frame.getdata())
        self.assertTrue(report["passed"])

    def test_explicit_oversized_scale_is_reported_as_clipping(self):
        path = self.write_frame("large.png", (10, 10, 29, 29))
        _, _, report = self.pack_images([path, path], self.settings | {"scale": 4})
        self.assertFalse(report["passed"])
        self.assertIn("transform_clipping", [issue["type"] for issue in report["issues"]])

    def test_looping_preview_is_explicit_and_warnings_do_not_fail_technical_checks(self):
        first = self.write_frame("idle-first.png", (10, 10, 19, 29))
        output, atlas, report = self.pack_images([first, first], self.settings | {"loop": True})
        with Image.open(output / "animation.gif") as preview:
            self.assertEqual(preview.info["loop"], 0)
        self.assertTrue(atlas["animation"]["loop"])
        self.assertTrue(report["passed"])
        self.assertEqual(report["technical_status"], "needs_review")

    def test_empty_duplicate_and_edge_frames_are_reported_without_approval(self):
        first = self.write_frame("edge.png", (0, 10, 5, 20))
        output, _, report = self.pack_images([first, first])
        self.assertIn("source_edge_touch", [w["type"] for w in report["warnings"]])
        self.assertIn("duplicate_frame", [w["type"] for w in report["warnings"]])
        self.assertFalse(report["creative_approval"])
        empty = self.write_frame("empty.png", None)
        config = validate_settings(self.settings)
        other = self.folder / "empty-atlas"
        other.mkdir()
        _pack_images([empty, empty], other, config, [0, 0.5], {})
        empty_report = json.loads((other / "qc.json").read_text())
        self.assertEqual(sum(w["type"] == "empty_frame" for w in empty_report["issues"]), 2)
        self.assertFalse(empty_report["passed"])

    def test_bad_settings_and_existing_output_fail_before_ffmpeg(self):
        source = self.folder / "source.mp4"
        source.write_bytes(b"untouched original")
        output = self.folder / "existing"
        output.mkdir()
        (output / "sheet.png").write_bytes(b"keep this version")
        with patch("studio.sprites.subprocess.run") as run:
            for replacement in ({"end_seconds": 0}, {"frame_count": 0}, {"frame_count": True},
                                {"cell_width": 3}, {"background_key": "pink"}, {"sprite_fps": float("nan")}):
                with self.assertRaises(ValueError):
                    pack_video(source, self.folder / "new", self.settings | replacement)
            with self.assertRaisesRegex(ValueError, "not be overwritten"):
                pack_video(source, output, self.settings)
            run.assert_not_called()
        self.assertEqual((output / "sheet.png").read_bytes(), b"keep this version")
        self.assertFalse((self.folder / "new").exists())

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg and ffprobe not installed")
    def test_video_roundtrip_preserves_source_exact_sampling_and_atlas(self):
        for index in range(4):
            self.write_frame(f"input_{index:02d}.png", (10 + index, 10, 19 + index, 29))
        source = self.folder / "video.mkv"
        subprocess.run([shutil.which("ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin",
                        "-framerate", "4", "-i", str(self.folder / "input_%02d.png"), "-c:v", "ffv1", str(source)], check=True)
        original = source.read_bytes()
        output = self.folder / "video-atlas"
        result = pack_video(source, output, self.settings | {"start_seconds": 0.25, "end_seconds": 0.75})
        atlas = json.loads((output / "atlas.json").read_text())
        self.assertEqual(atlas["sampling"]["sample_times_seconds"], [0.25, 0.5])
        self.assertEqual((output / "source.mkv").read_bytes(), original)
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual(result["source_sha256"], sha256(original).hexdigest())
        self.assertEqual(len(list((output / "raw-frames").glob("*.png"))), 2)
        self.assertEqual(atlas["frames"][0]["duration_ms"], 125)
        with Image.open(output / "raw-frames/frame_0001.png") as raw:
            self.assertEqual(raw.convert("RGB").getpixel((11, 10)), (0, 220, 60))
            self.assertEqual(raw.convert("RGB").getpixel((10, 10)), (255, 0, 255))
        with self.assertRaisesRegex(ValueError, "not be overwritten"):
            pack_video(source, output, self.settings)
        with self.assertRaisesRegex(ValueError, "exceeds"):
            pack_video(source, self.folder / "too-long", self.settings | {"end_seconds": 2})
        self.assertFalse((self.folder / "too-long").exists())


if __name__ == "__main__":
    unittest.main()
