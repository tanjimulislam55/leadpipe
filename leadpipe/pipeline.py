"""Ingestion pipeline: read -> map -> clean -> validate -> store.

A mapping is a dict {source_field: transform_name}. Where the mapping comes
from (hardcoded, cache, or LLM) is the caller's concern — this module applies
it, validates the output against the canonical schema, and raises
MappingDriftError with a diagnostic report when the mapping no longer fits
the data. That error text is exactly what gets fed back to the LLM in the
self-heal loop.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from pydantic import ValidationError

from . import cleaners
from .schema import CanonicalLead, Source, Status

# Mapped fields missing from more than this share of a batch = drift.
DRIFT_MISSING_THRESHOLD = 0.8
# More than this share of rows failing schema validation = drift.
DRIFT_INVALID_THRESHOLD = 0.5


class MappingDriftError(Exception):
    """The mapping no longer matches the incoming data. Message is the
    diagnostic report handed to the LLM for self-healing."""


def flatten_facebook(payload: dict) -> dict:
    """Flatten the Lead Ads webhook shape into {field: value}."""
    value = payload["entry"][0]["changes"][0]["value"]
    flat = {name: value[name] for name in ("campaign_id", "created_time") if name in value}
    for item in value.get("field_data", []):
        vals = item.get("values") or [None]
        flat[item.get("name", "")] = vals[0]
    return flat


def read_records(path: Path | str) -> Iterator[dict]:
    """Yield flat {field: value} records from a .jsonl or .csv source file."""
    path = Path(path)
    if path.suffix == ".jsonl":
        with open(path) as f:
            for line in f:
                if not line.strip():
                    continue
                obj = json.loads(line)
                yield flatten_facebook(obj) if "entry" in obj else obj
    elif path.suffix == ".csv":
        with open(path, newline="") as f:
            yield from csv.DictReader(f)
    else:
        raise ValueError(f"unsupported source file type: {path}")


def apply_mapping(record: dict, mapping: dict[str, str], source: Source) -> CanonicalLead:
    """Apply {source_field: transform} to one flat record. Raises KeyError /
    ValidationError on structural problems — callers count those for drift."""
    out: dict[str, Any] = {"source": source, "raw_payload": json.dumps(record, default=str)}
    flags: list[str] = []

    for field, transform in mapping.items():
        value = record.get(field)
        if transform == "ignore":
            continue
        elif transform == "split_full_name":
            out["first_name"], out["last_name"] = cleaners.split_full_name(value)
        elif transform == "first_name":
            out["first_name"] = cleaners.clean_name(value)
        elif transform == "last_name":
            out["last_name"] = cleaners.clean_name(value)
        elif transform == "email":
            out["email"], f = cleaners.clean_email(value)
            flags += f
        elif transform == "phone":
            out["phone_e164"], f = cleaners.clean_phone(value)
            flags += f
        elif transform == "campaign_id":
            out["campaign_id"] = str(value) if value not in (None, "") else None
        elif transform == "consent":
            out["consent"] = cleaners.clean_consent(value)
        elif transform == "created_at":
            out["created_at"] = cleaners.clean_date(value)
        else:
            raise ValueError(f"unknown transform {transform!r} for field {field!r}")

    if out.get("created_at") is None:
        out["created_at"] = datetime.now(timezone.utc)
        flags.append("date_missing")
    if not out.get("first_name") and not out.get("last_name"):
        flags.append("name_missing")

    hard_flags = {"phone_junk", "phone_unparseable", "phone_missing", "email_junk",
                  "email_invalid", "email_missing", "name_missing", "date_missing"}
    out["status"] = Status.flagged if hard_flags & set(flags) else Status.clean
    out["flags"] = flags
    return CanonicalLead(**out)


def process_batch(records: list[dict], mapping: dict[str, str],
                  source: Source) -> tuple[list[CanonicalLead], list[dict]]:
    """Map+validate a batch. Returns (valid leads, failed rows).

    Raises MappingDriftError when failures look structural (wrong mapping)
    rather than row-level dirt.
    """
    if not records:
        return [], []

    active = {f: t for f, t in mapping.items() if t != "ignore"}
    missing_counts = {f: 0 for f in active}
    leads: list[CanonicalLead] = []
    failures: list[dict] = []
    errors: list[str] = []

    for rec in records:
        for f in active:
            if f not in rec:
                missing_counts[f] += 1
        try:
            leads.append(apply_mapping(rec, mapping, source))
        except (ValidationError, ValueError, KeyError, TypeError) as e:
            failures.append(rec)
            if len(errors) < 5:
                errors.append(f"{type(e).__name__}: {e}")

    n = len(records)
    dead_fields = {f: c for f, c in missing_counts.items()
                   if c / n > DRIFT_MISSING_THRESHOLD}
    seen_fields: set[str] = set()
    for rec in records[:200]:
        seen_fields.update(rec.keys())
    unmapped = sorted(seen_fields - set(mapping))

    if dead_fields or len(failures) / n > DRIFT_INVALID_THRESHOLD:
        report = [
            f"MAPPING DRIFT DETECTED for source={source.value}",
            f"batch size: {n}, rows failing validation: {len(failures)}",
            f"mapped fields missing from data: {list(dead_fields) or 'none'}",
            f"fields present in data but not in mapping: {unmapped or 'none'}",
            f"current mapping: {json.dumps(mapping)}",
            "sample errors: " + ("; ".join(errors) or "none"),
            "sample record keys: " + json.dumps(sorted(records[0].keys())),
        ]
        raise MappingDriftError("\n".join(report))

    return leads, failures
