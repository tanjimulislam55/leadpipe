"""Run the full pipeline over the four source files.

Default: LLM-powered. Cold-starts unknown sources via Ollama, caches approved
mappings (fast path), self-heals on drift. --no-llm falls back to hardcoded
mappings (debug/plumbing mode).
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from leadpipe import db, scorer
from leadpipe.doctor import Doctor
from leadpipe.mapping_store import MappingStore
from leadpipe.pipeline import MappingDriftError, process_batch, read_records
from leadpipe.schema import Source

HARDCODED_MAPPINGS: dict[str, dict[str, str]] = {
    "facebook": {
        "full_name": "split_full_name",
        "email": "email",
        "phone_number": "phone",
        "campaign_id": "campaign_id",
        "created_time": "created_at",
    },
    "instagram": {
        "Full Name": "split_full_name",
        "E-mail": "email",
        "Phone #": "phone",
        "Campaign": "campaign_id",
        "Date Submitted": "created_at",
        "Consent?": "consent",
    },
    "google_form": {
        "Timestamp": "created_at",
        "What's your name?": "split_full_name",
        "Best number to reach you": "phone",
        "Your email address": "email",
        "How did you hear about us?": "campaign_id",
        "Do you agree to be contacted?": "consent",
    },
    "landing_page": {
        "fname": "first_name",
        "lname": "last_name",
        "email_addr": "email",
        "mobile": "phone",
        "utm_campaign": "campaign_id",
        "utm_source": "ignore",
        "opt_in": "consent",
        "submitted_at": "created_at",
        "lead_id": "ignore",
    },
}

SOURCE_FILES = {
    "facebook": "facebook_leads.jsonl",
    "instagram": "instagram_export.csv",
    "google_form": "google_form.csv",
    "landing_page": "landing_page.jsonl",
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data/generated")
    ap.add_argument("--batch-size", type=int, default=5000)
    ap.add_argument("--limit", type=int, default=None, help="max rows per source")
    ap.add_argument("--skip", type=int, default=0,
                    help="skip the first N rows per source (demo continuation)")
    ap.add_argument("--no-llm", action="store_true",
                    help="use hardcoded mappings (plumbing debug mode)")
    ap.add_argument("--pace", type=float, default=0.0,
                    help="seconds to sleep between batches (live-demo pacing)")
    args = ap.parse_args()

    con = db.connect()
    doctor = None if args.no_llm else Doctor(con, MappingStore())
    t0 = time.time()
    grand_total = 0

    for source_name, filename in SOURCE_FILES.items():
        path = Path(args.data_dir) / filename
        if not path.exists():
            print(f"[skip] {path} not found")
            continue
        source = Source(source_name)
        print(f"[{source_name}] ingesting {path} ...")

        total = valid = flagged = failed = 0

        def flush(batch: list[dict]) -> None:
            nonlocal valid, flagged, failed
            if doctor is not None:
                leads, failures = doctor.process(source, batch)
            else:
                try:
                    leads, failures = process_batch(
                        batch, HARDCODED_MAPPINGS[source_name], source)
                except MappingDriftError as e:
                    db.log_heal_event(con, source_name, "drift_detected", detail=str(e))
                    print(f"  [DRIFT, no-llm mode] {source_name}: batch dropped")
                    failed += len(batch)
                    return
            for lead in leads:
                lead.quality_score = scorer.score(lead)
            db.insert_leads(con, leads)
            if doctor is None:
                for rec in failures:
                    db.queue_for_review(con, source_name, "row validation failed", rec)
                failed += len(failures)
            else:
                failed += len(failures)
            valid += len(leads)
            flagged += sum(1 for l in leads if l.status.value == "flagged")

        batch: list[dict] = []
        for i, rec in enumerate(read_records(path)):
            if i < args.skip:
                continue
            batch.append(rec)
            total += 1
            if len(batch) >= args.batch_size:
                flush(batch)
                batch = []
                if args.pace:
                    time.sleep(args.pace)
            if args.limit and total >= args.limit:
                break
        if batch:
            flush(batch)

        grand_total += total
        print(f"[{source_name}] rows={total} stored={valid} "
              f"(flagged={flagged}) failed/queued={failed}")

    dt = time.time() - t0
    print(f"\nTotal: {grand_total} rows in {dt:.1f}s ({grand_total/max(dt,0.01):,.0f} rows/s)")
    n = con.execute(
        "SELECT count(*), sum(CASE WHEN status='clean' THEN 1 ELSE 0 END) FROM leads"
    ).fetchone()
    print(f"DB now holds {n[0]} leads ({n[1]} clean)")


if __name__ == "__main__":
    main()
