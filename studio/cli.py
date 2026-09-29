"""python -m studio.cli list_projects | get_next_action --json-file request.json"""
import argparse
import json
from pathlib import Path
import sys
from .agent_tools import TOOLS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tool", choices=sorted(TOOLS))
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--json", default=None, help="Small JSON argument object; prefer --json-file on Windows")
    group.add_argument("--json-file", type=Path)
    args = parser.parse_args()
    try:
        value = json.loads(args.json_file.read_text(encoding="utf-8-sig") if args.json_file else args.json or "{}")
        result = TOOLS[args.tool](**value)
        print(json.dumps(result, indent=2, ensure_ascii=True))
        return 0
    except Exception as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
