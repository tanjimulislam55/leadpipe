"""Inject schema drift into the Facebook feed — the demo's villain.

Simulates Meta renaming fields in the Lead Ads payload: from a given row
onward, `phone_number` becomes `contact_phone` and `full_name` becomes
`applicant_name`. The cached mapping stops fitting, the pipeline detects
drift, and the Doctor must heal it live with zero human touch.

Usage:
    python inject_drift.py                     # drift the second half
    python inject_drift.py --start-row 2000    # drift from row 2000 on
    python inject_drift.py --restore           # undo (restore from backup)
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

TARGET = Path("data/generated/facebook_leads.jsonl")
BACKUP = TARGET.with_suffix(".jsonl.bak")

RENAMES = {"phone_number": "contact_phone", "full_name": "applicant_name"}


def drift_line(line: str) -> str:
    obj = json.loads(line)
    for item in obj["entry"][0]["changes"][0]["value"].get("field_data", []):
        if item.get("name") in RENAMES:
            item["name"] = RENAMES[item["name"]]
    return json.dumps(obj)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-row", type=int, default=None,
                    help="first drifted row (default: halfway)")
    ap.add_argument("--restore", action="store_true")
    args = ap.parse_args()

    if args.restore:
        if BACKUP.exists():
            shutil.copy(BACKUP, TARGET)
            print(f"restored {TARGET} from backup")
        else:
            print("no backup found")
        return

    if not BACKUP.exists():
        shutil.copy(TARGET, BACKUP)

    lines = BACKUP.read_text().splitlines()
    start = args.start_row if args.start_row is not None else len(lines) // 2
    with open(TARGET, "w") as f:
        for i, line in enumerate(lines):
            f.write((drift_line(line) if i >= start else line) + "\n")
    print(f"💉 drift injected: rows {start}..{len(lines)} now use "
          f"{list(RENAMES.values())} — Meta 'renamed' the fields")


if __name__ == "__main__":
    main()
