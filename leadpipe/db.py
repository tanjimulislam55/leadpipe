"""DuckDB storage — one unified leads table, raw payload always preserved."""
from __future__ import annotations

import json
from pathlib import Path

import duckdb

from .schema import CanonicalLead

DB_PATH = Path("data/leadpipe.duckdb")

DDL = """
CREATE TABLE IF NOT EXISTS leads (
    lead_id       TEXT PRIMARY KEY,
    first_name    TEXT,
    last_name     TEXT,
    email         TEXT,
    phone_e164    TEXT,
    source        TEXT,
    campaign_id   TEXT,
    consent       BOOLEAN,
    created_at    TIMESTAMPTZ,
    quality_score INTEGER,
    status        TEXT,
    flags         TEXT,
    raw_payload   JSON,
    ingested_at   TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS heal_events (
    ts          TIMESTAMPTZ DEFAULT now(),
    source      TEXT,
    event       TEXT,      -- drift_detected | retry | healed | human_review
    attempt     INTEGER,
    detail      TEXT
);
CREATE TABLE IF NOT EXISTS review_queue (
    ts          TIMESTAMPTZ DEFAULT now(),
    source      TEXT,
    reason      TEXT,
    raw_payload JSON
);
"""


def connect(path: Path | str = DB_PATH) -> duckdb.DuckDBPyConnection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    con.execute(DDL)
    return con


def insert_leads(con: duckdb.DuckDBPyConnection, leads: list[CanonicalLead]) -> None:
    if not leads:
        return
    rows = [
        (l.lead_id, l.first_name, l.last_name, l.email, l.phone_e164,
         l.source.value, l.campaign_id, l.consent, l.created_at,
         l.quality_score, l.status.value, json.dumps(l.flags), l.raw_payload)
        for l in leads
    ]
    con.executemany(
        "INSERT OR REPLACE INTO leads (lead_id, first_name, last_name, email, phone_e164,"
        " source, campaign_id, consent, created_at, quality_score, status, flags, raw_payload)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )


def log_heal_event(con: duckdb.DuckDBPyConnection, source: str, event: str,
                   attempt: int = 0, detail: str = "") -> None:
    con.execute(
        "INSERT INTO heal_events (source, event, attempt, detail) VALUES (?, ?, ?, ?)",
        (source, event, attempt, detail[:2000]),
    )


def queue_for_review(con: duckdb.DuckDBPyConnection, source: str, reason: str,
                     raw_payload: dict | str) -> None:
    if not isinstance(raw_payload, str):
        raw_payload = json.dumps(raw_payload, default=str)
    con.execute(
        "INSERT INTO review_queue (source, reason, raw_payload) VALUES (?, ?, ?)",
        (source, reason[:2000], raw_payload),
    )
