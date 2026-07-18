"""Rule-based lead quality scoring, 0-100.

The brief allows a rule-based fallback for the XGBoost scorer; this is that
fallback, shipped first. Weights favor callable phone + consent, matching
speed-to-lead economics.
"""
from __future__ import annotations

from .cleaners import FREE_DOMAINS, JUNK_EMAIL_DOMAINS
from .schema import CanonicalLead


def score(lead: CanonicalLead) -> int:
    s = 0
    if lead.phone_e164:
        s += 35
        if "phone_unverified" not in lead.flags:
            s += 5
    if lead.email:
        domain = lead.email.rsplit("@", 1)[-1]
        if "email_junk" in lead.flags or domain in JUNK_EMAIL_DOMAINS:
            s += 0
        elif domain in FREE_DOMAINS:
            s += 15
        else:  # corporate domain
            s += 25
    if lead.consent:
        s += 20
    if lead.first_name and lead.last_name:
        s += 10
    if lead.campaign_id:
        s += 5
    return min(s, 100)
