"""Verify actual rendered audio, timing, character isolation and Wan reference slices."""
import argparse
from array import array
import json
from pathlib import Path
import wave

RATE = 48000


def pcm(path):
    with wave.open(str(path), "rb") as stream:
        assert (stream.getnchannels(), stream.getsampwidth(), stream.getframerate(), stream.getcomptype()) == (1, 2, RATE, "NONE"), str(path)
        return array("h", stream.readframes(stream.getnframes()))


def verify(folder):
    folder = Path(folder)
    report = json.loads((folder / "timing.json").read_text(encoding="utf-8"))
    mix = pcm(folder / "mix.wav")
    assert len(mix) == round(report["actual_duration"] * RATE)
    assert max(abs(value) for value in mix) < 32767
    stems = []
    for char_id in report["characters"]:
        stem = pcm(folder / "stems" / f"{char_id}.wav")
        assert len(stem) == len(mix)
        intervals = sorted((round(line["start"] * RATE), round(line["end"] * RATE)) for line in report["lines"] if line["character"] == char_id)
        end_of_previous = 0
        for start, end in intervals:
            assert not any(stem[end_of_previous:start]), f"Unexpected audio in {char_id} silence"
            assert any(stem[start:end]), f"Missing dialogue on {char_id}"
            end_of_previous = max(end_of_previous, end)
        assert not any(stem[end_of_previous:]), f"Unexpected audio after {char_id} dialogue"
        stems.append(stem)
    tolerance = len(stems)
    assert all(abs(sum(values) - mixed) <= tolerance for values, mixed in zip(zip(*stems), mix)), "Mix differs from isolated stems"
    for line in report["lines"]:
        samples = pcm(folder / line["file"])
        assert len(samples) == round(line["duration"] * RATE)
        assert any(samples), f"Silent line: {line['id']}"
    for job in report["exported_jobs"]:
        reference = pcm(folder / job["audio_file"])
        assert reference == mix[round(job["start"] * RATE):round(job["end"] * RATE)]
        assert len(reference) == round(job["duration"] * RATE)
        assert job["duration"] <= 15
        assert job["duration"] + job["planned_previs_duration"] <= 30
    if not report["timing_passed"]:
        assert not list((folder / "jobs").glob("*.wav")), "Failed timing exported references"
    plan = json.loads((folder / "wan-plan.json").read_text(encoding="utf-8"))
    assert plan["submission_enabled"] is False and plan["creative_approval"] is None
    assert len(plan["jobs"]) == len(report["exported_jobs"])
    return {"verified": True, "mix_seconds": len(mix) / RATE, "characters": len(stems), "lines": len(report["lines"]), "reference_jobs": len(report["exported_jobs"]), "timing_passed": report["timing_passed"], "peak_dbfs": report["peak_dbfs"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.folder), indent=2))
