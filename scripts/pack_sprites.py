"""Pack an approved downloaded local clip into a transparent game sprite atlas."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from studio.sprites import pack_video


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="Original downloaded local video")
    parser.add_argument("--output", required=True, type=Path, help="New or empty artifact version directory")
    parser.add_argument("--settings", required=True, type=Path, help="Approved plain JSON settings file")
    args = parser.parse_args()
    try:
        settings = json.loads(args.settings.read_text(encoding="utf-8-sig"))
        result = pack_video(args.source, args.output, settings)
    except (ValueError, OSError, json.JSONDecodeError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
