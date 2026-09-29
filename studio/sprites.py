"""Deterministic local sprite packing from an approved downloaded video.

This module performs no generation, upload, approval, or paid retry. The caller
chooses a new output version and the exact approved sampling settings.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any

from PIL import Image, ImageChops


MAX_SHEET_PIXELS = 64_000_000
SETTING_KEYS = {
    "start_seconds", "end_seconds", "frame_count", "cell_width", "cell_height",
    "columns", "sprite_fps", "background_key", "key_tolerance", "feather",
    "pixel_art", "padding", "feet_pivot", "source_anchor", "scale", "loop",
}


def _number(value: Any, name: str, *, minimum: float, maximum: float,
            integer: bool = False) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a {'whole number' if integer else 'number'}.")
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")
    if integer and int(value) != value:
        raise ValueError(f"{name} must be a whole number.")
    return int(value) if integer else float(value)


def _point(value: Any, name: str) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{name} must contain two normalized coordinates.")
    return [_number(v, name, minimum=0, maximum=1) for v in value]


def validate_settings(settings: dict) -> dict:
    """Validate before ffmpeg or filesystem mutations; return explicit settings."""
    if not isinstance(settings, dict):
        raise ValueError("Sprite settings must be a JSON object.")
    unknown = set(settings) - SETTING_KEYS
    if unknown:
        raise ValueError("Unknown sprite settings: " + ", ".join(sorted(unknown)))
    for name in ("start_seconds", "end_seconds", "frame_count", "cell_width", "cell_height"):
        if name not in settings:
            raise ValueError(f"Missing required sprite setting: {name}.")
    result = {
        "start_seconds": _number(settings["start_seconds"], "start_seconds", minimum=0, maximum=86_400),
        "end_seconds": _number(settings["end_seconds"], "end_seconds", minimum=0, maximum=86_400),
        "frame_count": _number(settings["frame_count"], "frame_count", minimum=1, maximum=256, integer=True),
        "cell_width": _number(settings["cell_width"], "cell_width", minimum=4, maximum=2048, integer=True),
        "cell_height": _number(settings["cell_height"], "cell_height", minimum=4, maximum=2048, integer=True),
        "sprite_fps": _number(settings.get("sprite_fps", 12), "sprite_fps", minimum=0.1, maximum=120),
        "key_tolerance": _number(settings.get("key_tolerance", 24), "key_tolerance", minimum=0, maximum=255, integer=True),
        "feather": _number(settings.get("feather", 0), "feather", minimum=0, maximum=64, integer=True),
        "padding": _number(settings.get("padding", 2), "padding", minimum=0, maximum=512, integer=True),
        "feet_pivot": _point(settings.get("feet_pivot", [0.5, 1]), "feet_pivot"),
    }
    if result["end_seconds"] - result["start_seconds"] < 0.000001:
        raise ValueError("end_seconds must be greater than start_seconds by at least one microsecond.")
    result["columns"] = _number(settings.get("columns", min(result["frame_count"], 8)), "columns", minimum=1, maximum=result["frame_count"], integer=True)
    result["pixel_art"] = settings.get("pixel_art", True)
    if not isinstance(result["pixel_art"], bool):
        raise ValueError("pixel_art must be true or false.")
    result["loop"] = settings.get("loop", False)
    if not isinstance(result["loop"], bool):
        raise ValueError("loop must be true or false.")
    key = settings.get("background_key", "#FF00FF")
    if key is not None and (not isinstance(key, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", key)):
        raise ValueError("background_key must be #RRGGBB or null.")
    result["background_key"] = key.upper() if key is not None else None
    if "source_anchor" in settings:
        result["source_anchor"] = _point(settings["source_anchor"], "source_anchor")
    if "scale" in settings:
        result["scale"] = _number(settings["scale"], "scale", minimum=0.001, maximum=128)
    if result["padding"] * 2 >= min(result["cell_width"], result["cell_height"]):
        raise ValueError("padding must leave visible space inside the sprite cell.")
    rows = math.ceil(result["frame_count"] / result["columns"])
    if result["columns"] * result["cell_width"] * rows * result["cell_height"] > MAX_SHEET_PIXELS:
        raise ValueError("Sprite sheet exceeds the 64 million pixel safety limit.")
    return result


def _file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run(arguments: list[str], timeout: int = 90) -> str:
    completed = subprocess.run(arguments, capture_output=True, text=True, timeout=timeout)
    if completed.returncode:
        raise ValueError("Local video decoding failed: " + completed.stderr.strip()[-1600:])
    return completed.stdout


def _probe_video(source: Path, ffprobe: str) -> dict:
    data = json.loads(_run([
        ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
        "format=duration:stream=width,height,avg_frame_rate,duration", "-of", "json", str(source),
    ], timeout=45))
    streams = data.get("streams", [])
    if not streams:
        raise ValueError("Source has no decodable video stream.")
    stream = streams[0]
    duration = float(stream.get("duration", data.get("format", {}).get("duration", 0)))
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Source video must have a measured finite duration.")
    width, height = int(stream.get("width", 0)), int(stream.get("height", 0))
    if width <= 0 or height <= 0 or width * height > 16_000_000:
        raise ValueError("Source video dimensions are invalid or exceed 16 million pixels.")
    return {"duration_seconds": duration, "width": width, "height": height,
            "average_frame_rate": stream.get("avg_frame_rate"), "measured_by": "ffprobe"}


def _remove_background(frame: Image.Image, settings: dict) -> Image.Image:
    rgba = frame.convert("RGBA")
    key = settings["background_key"]
    if key is None:
        return rgba
    target = tuple(int(key[i:i + 2], 16) for i in (1, 3, 5))
    tolerance, feather = settings["key_tolerance"], settings["feather"]
    pixels = []
    for r, g, b, alpha in rgba.getdata():
        distance = max(abs(r - target[0]), abs(g - target[1]), abs(b - target[2]))
        if distance <= tolerance:
            pixels.append((0, 0, 0, 0))
        elif feather and distance < tolerance + feather:
            pixels.append((r, g, b, round(alpha * (distance - tolerance) / feather)))
        else:
            pixels.append((r, g, b, alpha) if alpha else (0, 0, 0, 0))
    rgba.putdata(pixels)
    return rgba


def _common_transform(frames: list[Image.Image], settings: dict) -> dict:
    bounds = [frame.getchannel("A").getbbox() for frame in frames]
    nonempty = [b for b in bounds if b]
    source_width, source_height = frames[0].size
    union = ([min(b[0] for b in nonempty), min(b[1] for b in nonempty),
              max(b[2] for b in nonempty), max(b[3] for b in nonempty)]
             if nonempty else [0, 0, source_width, source_height])
    left, top, right, bottom = union
    if "source_anchor" in settings:
        anchor = [source_width * settings["source_anchor"][0], source_height * settings["source_anchor"][1]]
    else:
        anchor = [(left + right) / 2, float(bottom)]
    padding = settings["padding"]
    width, height = settings["cell_width"], settings["cell_height"]
    pivot = [padding + round((width - 1 - 2 * padding) * settings["feet_pivot"][0]),
             padding + round((height - 1 - 2 * padding) * settings["feet_pivot"][1])]
    ratios = []
    for extent, space in ((anchor[0] - left, pivot[0] - padding),
                          (right - anchor[0], width - padding - pivot[0]),
                          (anchor[1] - top, pivot[1] - padding),
                          (bottom - anchor[1], height - padding - pivot[1])):
        if extent > 0:
            if space <= 0:
                raise ValueError("Chosen pivot cannot fit the shared subject bounds. Adjust feet_pivot or source_anchor.")
            ratios.append(space / extent)
    scale = settings.get("scale", min(ratios) if ratios else 1.0)
    crop_size = [max(1, round((right - left) * scale)), max(1, round((bottom - top) * scale))]
    destination = [round(pivot[0] - (anchor[0] - left) * scale),
                   round(pivot[1] - (anchor[1] - top) * scale)]
    return {"union_bounds_source": union, "source_anchor_pixels": anchor,
            "pivot_pixels": pivot, "scale": scale, "scaled_crop_size": crop_size,
            "destination_pixels": destination, "shared_across_frames": True,
            "alignment": "One fixed source anchor maps to the same cell pivot; individual frames are never fitted separately."}


def _pixel_difference(first: Image.Image, second: Image.Image) -> float:
    """Normalized RGBA absolute error, useful for review without implying semantics."""
    totals = ImageChops.difference(first, second).histogram()
    error = sum((index % 256) * count for index, count in enumerate(totals))
    return round(error / (first.width * first.height * 4 * 255), 6)


def _pack_images(raw_paths: list[Path], output: Path, settings: dict,
                 sample_times: list[float], source_info: dict) -> dict:
    """Packing core also supports isolated deterministic image fixture tests."""
    frames = []
    for path in raw_paths:
        with Image.open(path) as original:
            frames.append(_remove_background(original, settings))
    if not frames or any(frame.size != frames[0].size for frame in frames):
        raise ValueError("Extracted frames must have the same source dimensions.")
    transform = _common_transform(frames, settings)
    rows = math.ceil(len(frames) / settings["columns"])
    sheet = Image.new("RGBA", (settings["columns"] * settings["cell_width"], rows * settings["cell_height"]), (0, 0, 0, 0))
    normalized = []
    records = []
    warnings = []
    errors = []
    frame_folder = output / "frames"
    frame_folder.mkdir()
    seen: dict[str, int] = {}
    duration_ms = 1000 / settings["sprite_fps"]
    for index, frame in enumerate(frames):
        crop = frame.crop(tuple(transform["union_bounds_source"]))
        crop = crop.resize(tuple(transform["scaled_crop_size"]), Image.Resampling.NEAREST if settings["pixel_art"] else Image.Resampling.LANCZOS)
        cell = Image.new("RGBA", (settings["cell_width"], settings["cell_height"]), (0, 0, 0, 0))
        cell.paste(crop, tuple(transform["destination_pixels"]))
        frame_name = f"frame_{index + 1:04d}.png"
        cell.save(frame_folder / frame_name)
        x = (index % settings["columns"]) * settings["cell_width"]
        y = (index // settings["columns"]) * settings["cell_height"]
        sheet.paste(cell, (x, y))
        source_bounds = frame.getchannel("A").getbbox()
        cell_bounds = cell.getchannel("A").getbbox()
        if source_bounds is None:
            errors.append({"type": "empty_frame", "frame": index + 1, "message": "No visible sprite pixels remain."})
        if source_bounds and (source_bounds[0] == 0 or source_bounds[1] == 0 or source_bounds[2] == frame.width or source_bounds[3] == frame.height):
            warnings.append({"type": "source_edge_touch", "frame": index + 1,
                             "message": "Subject reaches the source edge; inspect for original-video cropping."})
        if cell_bounds and (cell_bounds[0] == 0 or cell_bounds[1] == 0 or cell_bounds[2] == cell.width or cell_bounds[3] == cell.height):
            warnings.append({"type": "cell_edge_touch", "frame": index + 1})
        digest = sha256(cell.tobytes()).hexdigest()
        if digest in seen:
            warnings.append({"type": "duplicate_frame", "frame": index + 1, "matches_frame": seen[digest]})
        else:
            seen[digest] = index + 1
        records.append({"name": frame_name, "file": f"frames/{frame_name}", "duration_ms": round(duration_ms, 6),
                        "source_sample_seconds": sample_times[index], "rect": {"x": x, "y": y, "w": cell.width, "h": cell.height},
                        "frame": {"x": x, "y": y, "w": cell.width, "h": cell.height},
                        "pivot_pixels": transform["pivot_pixels"], "pivot": {"x": transform["pivot_pixels"][0], "y": transform["pivot_pixels"][1]}, "source_alpha_bounds": source_bounds,
                        "cell_alpha_bounds": cell_bounds, "rgba_sha256": digest})
        normalized.append(cell)
    sheet.save(output / "sheet.png")
    # GIF is a convenience preview; the alpha PNGs and atlas remain authoritative.
    previews = []
    for cell in normalized:
        preview = Image.new("RGB", cell.size, "#262B36")
        preview.paste(cell, mask=cell.getchannel("A"))
        previews.append(preview)
    gif_duration = max(10, round(duration_ms / 10) * 10)
    preview_options = {"loop": 0} if settings["loop"] else {}
    previews[0].save(output / "animation.gif", save_all=True, append_images=previews[1:],
                     duration=gif_duration, disposal=2, optimize=False, **preview_options)
    adjacent = [_pixel_difference(normalized[i - 1], normalized[i]) for i in range(1, len(normalized))]
    seam = _pixel_difference(normalized[-1], normalized[0]) if len(normalized) > 1 else 0
    typical = sorted(adjacent)[len(adjacent) // 2] if adjacent else 0
    if settings["loop"] and seam > max(0.04, typical * 2.5):
        warnings.append({"type": "loop_seam", "normalized_rgba_error": seam,
                         "message": "End-to-start change exceeds typical adjacent change; review playback."})
    destination = transform["destination_pixels"]
    if (destination[0] < 0 or destination[1] < 0 or
            destination[0] + transform["scaled_crop_size"][0] > settings["cell_width"] or
            destination[1] + transform["scaled_crop_size"][1] > settings["cell_height"]):
        errors.append({"type": "transform_clipping", "message": "Explicit scale or anchor clips the shared subject bounds."})
    report = {"schema_version": 1, "technical_status": "failed" if errors else "needs_review" if warnings else "checks_passed",
              "passed": not errors, "issues": errors, "creative_approval": False, "warnings": warnings,
              "loop_seam_normalized_rgba_error": seam, "adjacent_frame_errors": adjacent,
              "limitations": ["Pixel comparisons cannot certify character identity, intended action, direction, anatomy, or artistic consistency.",
                              "Chroma key removes all matching pixels, including matching colors inside the subject; inspect silhouettes and edges.",
                              "GIF preview quantizes colors and timing; transparent PNGs and atlas durations are authoritative.",
                              "Technical checks do not constitute director approval. No generation retry is performed."]}
    atlas = {"schema_version": 1, "type": "game_sprite_atlas", "source": source_info,
             "sheet": {"file": "sheet.png", "width": sheet.width, "height": sheet.height,
                       "columns": settings["columns"], "rows": rows, "cell_width": settings["cell_width"], "cell_height": settings["cell_height"]},
             "meta": {"image": "sheet.png", "size": {"w": sheet.width, "h": sheet.height},
                      "sprite_fps": settings["sprite_fps"], "cell_width": settings["cell_width"], "cell_height": settings["cell_height"],
                      "columns": settings["columns"], "rows": rows, "scale": transform["scale"], "source_sha256": source_info.get("sha256")},
             "animation": {"sprite_fps": settings["sprite_fps"], "loop": settings["loop"], "duration_ms": round(duration_ms * len(frames), 6),
                           "frame_count": len(frames), "preview": "animation.gif", "preview_frame_duration_ms": gif_duration},
             "sampling": {"start_seconds": settings["start_seconds"], "end_seconds": settings["end_seconds"],
                          "end_exclusive": True, "sample_times_seconds": sample_times,
                          "note": "Requested times are decoded by ffmpeg at the nearest available frame at or after each requested timestamp."},
             "settings": settings, "transform": transform, "frames": records, "qc": "qc.json"}
    (output / "atlas.json").write_text(json.dumps(atlas, indent=2), encoding="utf-8")
    (output / "qc.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return {"output": str(output), "atlas": atlas, "qc": report, "settings": settings,
            "files": {"sheet": str(output / "sheet.png"), "preview": str(output / "animation.gif"),
                      "atlas": str(output / "atlas.json"), "qc": str(output / "qc.json")},
            "frame_count": len(frames), "source_sha256": source_info.get("sha256"),
            "technical_status": report["technical_status"], "creative_approval": False,
            "warnings": warnings}


def pack_video(source: Path, output: Path, settings: dict) -> dict:
    """Preserve a local clip and package its approved interval into a new atlas.

    Output must be absent or empty. Failures leave the copied source and any raw
    frames in place for inspection; reruns must use a new version directory.
    """
    config = validate_settings(settings)
    source = Path(source).resolve()
    output = Path(output).resolve()
    if not source.is_file():
        raise ValueError("Sprite source must be an existing local video file.")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("Sprite output must be a new or empty version directory; existing artifacts will not be overwritten.")
    if output == source or output in source.parents:
        raise ValueError("Source video must be outside the new output directory.")
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise ValueError("Install ffmpeg and ffprobe on PATH to pack local sprite video.")
    video = _probe_video(source, ffprobe)
    if config["end_seconds"] > video["duration_seconds"] + 0.000001:
        raise ValueError("Approved sampling interval exceeds the measured source duration.")
    if video["width"] * video["height"] * config["frame_count"] > 128_000_000:
        raise ValueError("Decoded sprite frames exceed 128 million pixels. Reduce frame_count or downscale a preserved source copy first.")
    output.mkdir(parents=True, exist_ok=True)
    preserved = output / ("source" + source.suffix.lower())
    shutil.copy2(source, preserved)
    source_info = {"original_filename": source.name, "preserved_file": preserved.name,
                   "sha256": _file_hash(preserved), "video": video}
    raw_folder = output / "raw-frames"
    raw_folder.mkdir()
    step = (config["end_seconds"] - config["start_seconds"]) / config["frame_count"]
    times = [round(config["start_seconds"] + index * step, 9) for index in range(config["frame_count"])]
    (output / "extraction.json").write_text(json.dumps({"source": source_info, "settings": config,
                                                       "sample_times_seconds": times}, indent=2), encoding="utf-8")
    raw_paths = []
    for index, when in enumerate(times):
        target = raw_folder / f"frame_{index + 1:04d}.png"
        _run([ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-ss", f"{when:.9f}",
              "-i", str(preserved), "-map", "0:v:0", "-frames:v", "1", "-update", "1", str(target)])
        if not target.is_file():
            raise ValueError(f"No source frame could be decoded at {when:.9f} seconds. Original and extracted frames were preserved.")
        raw_paths.append(target)
    return _pack_images(raw_paths, output, config, times, source_info)
