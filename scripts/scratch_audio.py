"""Local scratch dialogue -> measured timeline, stems, subtitles and Wan reference slices.

Standard library only. Windows System.Speech synthesizes plain text; an optional
audio_file on each line accepts existing 48 kHz / mono / 16-bit PCM recordings.
No uploads, API requests, approval inference, time stretching or silent trimming.
"""
from __future__ import annotations

import argparse
from array import array
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid
import wave

RATE = 48000
ROOT = Path(__file__).resolve().parents[1]


def dump(path, data):
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def safe_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", value):
        raise ValueError(f"Unsafe or invalid ID: {value!r}")
    return value


def number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def validate(source):
    if source.get("schema_version") != 1:
        raise ValueError("schema_version must be 1")
    safe_id(source["sequence_id"])
    duration = number(source["target_duration"], "target_duration")
    if not 2 <= duration <= 30:
        raise ValueError("Each review sequence must be between 2 and 30 seconds")
    if source.get("fps") != 30:
        raise ValueError("This Wan workflow uses 30 fps")
    chars = source["characters"]
    if not isinstance(chars, dict) or not chars:
        raise ValueError("At least one character is required")
    for key, char in chars.items():
        safe_id(key)
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", char["color"]):
            raise ValueError(f"Invalid color for {key}")
        if not isinstance(char.get("voice"), str) or not char["voice"]:
            raise ValueError(f"A scratch voice is required for {key}")
        rate = char.get("rate", 0)
        if isinstance(rate, bool) or not isinstance(rate, int) or not -10 <= rate <= 10:
            raise ValueError(f"{key} rate must be an integer from -10 to 10")
    for group in ("shots", "jobs"):
        items = source[group]
        if not items:
            raise ValueError(f"{group} must cover the sequence")
        cursor, seen = 0.0, set()
        for item in items:
            ident = safe_id(item["id"])
            if ident in seen:
                raise ValueError(f"Duplicate {group} ID: {ident}")
            seen.add(ident)
            start = number(item["start"], "start")
            end = number(item["end"], "end")
            if abs(start - cursor) > 1e-6 or end <= start or end > duration:
                raise ValueError(f"{group} must be ordered, contiguous and cover the sequence")
            if any(abs(t * 30 - round(t * 30)) > 1e-6 for t in (start, end)):
                raise ValueError(f"{group} boundaries must be on 30 fps frames")
            length = end - start
            if group == "jobs" and (not 2 <= length <= 15 or abs(length - round(length)) > 1e-6):
                raise ValueError("Matching-previs jobs must be integer durations from 2 to 15 seconds")
            cursor = end
        if abs(cursor - duration) > 1e-6:
            raise ValueError(f"{group} must end at target_duration")
    seen = set()
    for line in source["lines"]:
        ident = safe_id(line["id"])
        if ident in seen:
            raise ValueError(f"Duplicate dialogue ID: {ident}")
        seen.add(ident)
        if line["character"] not in chars:
            raise ValueError(f"Unknown character on {ident}")
        if not isinstance(line["text"], str) or not line["text"].strip():
            raise ValueError(f"Empty text on {ident}")
        start = number(line["start"], "line start")
        end = number(line["slot_end"], "slot_end")
        if not 0 <= start < end <= duration:
            raise ValueError(f"Invalid dialogue slot on {ident}")
        if not isinstance(line.get("allow_overlap", False), bool):
            raise ValueError("allow_overlap must be true or false")
    for action in source.get("actions", []):
        start = number(action["start"], "action start")
        end = number(action["end"], "action end")
        if not 0 <= start < end <= duration:
            raise ValueError("Action intervals must be inside the review sequence")


def read_wave(path):
    with wave.open(str(path), "rb") as stream:
        if (stream.getnchannels(), stream.getsampwidth(), stream.getframerate(), stream.getcomptype()) != (1, 2, RATE, "NONE"):
            raise ValueError(f"{path}: expected mono 48 kHz 16-bit PCM WAV")
        samples = array("h", stream.readframes(stream.getnframes()))
    if sys.byteorder != "little":
        samples.byteswap()
    if not samples or not any(samples):
        raise ValueError(f"Empty or silent dialogue file: {path}")
    return samples


def write_wave(path, samples):
    data = array("h", samples)
    if sys.byteorder != "little":
        data.byteswap()
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(RATE)
        stream.writeframes(data.tobytes())


def timing_issues(source, lines):
    issues = []
    boundaries = [job["end"] for job in source["jobs"][:-1]]
    for line in lines:
        if line["end"] > line["slot_end"] + 1 / RATE:
            issues.append(f"{line['id']} exceeds its dialogue slot by {line['end'] - line['slot_end']:.3f}s. Rewrite it, move it or explicitly change the voice rate.")
        if line["end"] > source["target_duration"] + 1 / RATE:
            issues.append(f"{line['id']} runs past the sequence end; the review mix preserves the full line.")
        for cut in boundaries:
            if line["start"] < cut < line["end"]:
                issues.append(f"{line['id']} crosses the {cut:g}s generation boundary. Move the boundary or the dialogue; no reference slices were exported.")
    for i, a in enumerate(lines):
        for b in lines[i + 1:]:
            if max(a["start"], b["start"]) < min(a["end"], b["end"]):
                if not (a.get("allow_overlap") and b.get("allow_overlap")):
                    issues.append(f"{a['id']} overlaps {b['id']}; set allow_overlap=true on both only if intentional.")
    return issues


def srt_time(seconds):
    milliseconds = round(seconds * 1000)
    hours, milliseconds = divmod(milliseconds, 3600000)
    minutes, milliseconds = divmod(milliseconds, 60000)
    seconds, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"


def render(source_path, output_root):
    source_path = Path(source_path).resolve()
    raw = source_path.read_bytes()
    source = json.loads(raw.decode("utf-8-sig"))
    validate(source)
    digest = hashlib.sha256(raw).hexdigest()
    revision = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6]
    out = Path(output_root).resolve() / source["sequence_id"] / revision
    out.mkdir(parents=True, exist_ok=False)
    for folder in ("lines", "stems", "jobs"):
        (out / folder).mkdir()
    dump(out / "source.json", source)
    requests = []
    for line in source["lines"]:
        dest = out / "lines" / f"{line['id']}.wav"
        if line.get("audio_file"):
            recording = (source_path.parent / line["audio_file"]).resolve()
            read_wave(recording)
            shutil.copyfile(recording, dest)
        else:
            char = source["characters"][line["character"]]
            requests.append({"text": line["text"], "voice": char["voice"], "rate": char.get("rate", 0), "output": str(dest)})
    if requests:
        request_path = out / "synthesis-request.json"
        dump(request_path, {"lines": requests})
        subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-File", str(ROOT / "scripts" / "synthesize.ps1"), "-RequestPath", str(request_path)], check=True, timeout=180)
    lines, samples_by_id = [], {}
    for original in source["lines"]:
        samples = read_wave(out / "lines" / f"{original['id']}.wav")
        measured = dict(original)
        measured.update(duration=len(samples) / RATE, end=original["start"] + len(samples) / RATE, file=f"lines/{original['id']}.wav")
        lines.append(measured)
        samples_by_id[original["id"]] = samples
    lines.sort(key=lambda line: (line["start"], line["id"]))
    issues = timing_issues(source, lines)
    length = max(round(source["target_duration"] * RATE), max((round(line["start"] * RATE) + len(samples_by_id[line["id"]]) for line in lines), default=0))
    stems = {key: array("i", [0]) * length for key in source["characters"]}
    mix = array("i", [0]) * length
    for line in lines:
        start = round(line["start"] * RATE)
        for index, value in enumerate(samples_by_id[line["id"]]):
            stems[line["character"]][start + index] += value
            mix[start + index] += value
    peak = max((abs(value) for value in mix), default=0)
    all_peak = max([peak] + [max((abs(value) for value in stem), default=0) for stem in stems.values()])
    gain = min(1.0, 0.89 * 32767 / all_peak) if all_peak else 1.0
    mixed = array("h", (round(value * gain) for value in mix))
    write_wave(out / "mix.wav", mixed)
    for key, stem in stems.items():
        write_wave(out / "stems" / f"{key}.wav", (round(value * gain) for value in stem))
    with (out / "cue-sheet.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=["id", "character", "start", "end", "duration", "slot_end", "text"])
        writer.writeheader()
        writer.writerows({key: line[key] for key in writer.fieldnames} for line in lines)
    subtitles = []
    for index, line in enumerate(lines, 1):
        subtitles.append(f"{index}\n{srt_time(line['start'])} --> {srt_time(line['end'])}\n{line['character']}: {line['text']}\n")
    (out / "dialogue.srt").write_text("\n".join(subtitles), encoding="utf-8")
    jobs = []
    if not issues:
        for job in source["jobs"]:
            filename = f"jobs/{job['id']}.wav"
            write_wave(out / filename, mixed[round(job["start"] * RATE):round(job["end"] * RATE)])
            jobs.append({**job, "duration": job["end"] - job["start"], "audio_file": filename,
                         "dialogue": [{**line, "start": line["start"] - job["start"], "end": line["end"] - job["start"], "slot_end": line["slot_end"] - job["start"]} for line in lines if job["start"] <= line["start"] < job["end"]],
                         "planned_previs_duration": job["end"] - job["start"], "previs_file": None,
                         "reference_images": [], "reference_audio_url": None, "reference_video_url": None,
                         "ready_for_submission": False})
    plan = {"provider": "Alibaba Cloud Model Studio", "model": "wan3.0-video", "mode": "multimodal_reference",
            "source_sha256": digest, "audio_purpose": "temporary_timing_reference", "timing_passed": not issues,
            "creative_approval": None, "submission_enabled": False, "jobs": jobs,
            "note": "Local preparation only. Character references, approved Blender renders, provider validation, hosted media and explicit generation approval are still required."}
    dump(out / "wan-plan.json", plan)
    report = {**source, "lines": lines, "source_sha256": digest, "built_at": datetime.now(timezone.utc).isoformat(),
              "engine": "Windows System.Speech / supplied PCM recordings", "sample_rate": RATE,
              "actual_duration": length / RATE, "mix_gain": gain,
              "peak_dbfs": 20 * math.log10(max(abs(v) for v in mixed) / 32768) if any(mixed) else None,
              "timing_passed": not issues, "issues": issues, "approval": None, "exported_jobs": jobs}
    dump(out / "timing.json", report)
    markers = [{"frame": round(shot["start"] * 30) + 1, "name": shot["id"]} for shot in source["shots"]]
    markers += [{"frame": round(line["start"] * 30) + 1, "name": f"{line['character']} {line['id']}"} for line in lines]
    dump(out / "blender-timing.json", {"fps": 30, "frame_start": 1, "frame_end": math.ceil(length / RATE * 30),
                                       "audio_file": "mix.wav", "source_sha256": digest, "markers": markers,
                                       "shots": source["shots"], "jobs": source["jobs"], "characters": source["characters"]})
    template = (ROOT / "scripts" / "review-template.html").read_text(encoding="utf-8")
    embedded = json.dumps(report, ensure_ascii=False).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    (out / "review.html").write_text(template.replace("__TIMING_DATA__", embedded), encoding="utf-8")
    dump(out.parent / "latest.json", {"directory": revision, "review": f"{revision}/review.html", "timing_passed": not issues})
    (out.parent / "index.html").write_text(f'<!doctype html><html lang="en"><meta charset="utf-8"><title>Latest timing review</title><meta http-equiv="refresh" content="0;url={revision}/review.html"><a href="{revision}/review.html">Open latest timing review</a></html>', encoding="utf-8")
    print(json.dumps({"output": str(out), "duration": length / RATE, "timing_passed": not issues, "issues": issues}, indent=2))
    return out, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output-root", type=Path, default=ROOT / "outputs")
    args = parser.parse_args()
    try:
        _, report = render(args.source, args.output_root)
        return 0 if report["timing_passed"] else 2
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as error:
        print(f"Scratch audio failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
