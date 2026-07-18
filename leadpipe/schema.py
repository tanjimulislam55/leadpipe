"""Canonical lead schema — the frozen contract from the hackathon brief.

Every source maps into this. Structural failures here (missing/mismapped
fields) are what trigger the self-heal loop; row-level dirt (junk phone,
typo email) is preserved but flagged.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class Source(str, Enum):
    facebook = "facebook"
    instagram = "instagram"
    google_form = "google_form"
    landing_page = "landing_page"


class Status(str, Enum):
    clean = "clean"
    flagged = "flagged"
    duplicate = "duplicate"


class CanonicalLead(BaseModel):
    lead_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone_e164: Optional[str] = None
    source: Source
    campaign_id: Optional[str] = None
    consent: bool = False  # missing = false (TCPA-safe default)
    created_at: datetime
    quality_score: int = Field(default=0, ge=0, le=100)
    status: Status = Status.clean
    flags: list[str] = Field(default_factory=list)
    raw_payload: str  # original payload as JSON string — nothing is ever lost

    @field_validator("created_at")
    @classmethod
    def must_be_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("created_at must be timezone-aware (UTC)")
        return v.astimezone(timezone.utc)

    @field_validator("phone_e164")
    @classmethod
    def e164_format(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not (v.startswith("+") and v[1:].isdigit() and 8 <= len(v) <= 16):
            raise ValueError(f"not E.164: {v!r}")
        return v

    @field_validator("raw_payload")
    @classmethod
    def must_be_json(cls, v: str) -> str:
        json.loads(v)
        return v


# The set of canonical field names the LLM mapper is allowed to target.
MAPPABLE_FIELDS = {
    "full_name": "person's full name (needs splitting into first/last)",
    "first_name": "person's first/given name",
    "last_name": "person's last/family name",
    "email": "email address",
    "phone": "phone number in any format",
    "campaign_id": "marketing campaign identifier",
    "consent": "opt-in / agreement to be contacted",
    "created_at": "when the lead was submitted/created",
    "ignore": "field is irrelevant to the canonical schema",
}

SCHEMA_DOC = """Canonical lead schema (frozen):
- lead_id uuid: generated on ingest
- first_name/last_name text: split from full_name where needed; trim, fix casing, strip emoji
- email text: validated; junk domains flagged
- phone_e164 text: normalized to E.164 (+15551234567); unparseable = flagged
- source enum: facebook | instagram | google_form | landing_page
- campaign_id text: from payload (campaign_id, Campaign, utm_campaign, ...)
- consent bool: normalize Yes/yes/Y/TRUE/'I agree'/true; missing = false (TCPA-safe)
- created_at timestamptz: parse epoch / ISO / MM-DD-YYYY / DD-Mon-YYYY, store UTC
- quality_score int 0-100
- status enum: clean | flagged | duplicate
- raw_payload jsonb: original payload preserved
"""
