"""Pre-built cleaning transforms.

The LLM decides WHICH transform applies to WHICH source field; these
battle-tested functions do the actual work. A 7B model composing named
transforms is reliable; a 7B model freestyling pandas is not.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Optional

import phonenumbers
from dateutil import parser as dateparser
from email_validator import validate_email, EmailNotValidError

JUNK_EMAIL_DOMAINS = {"test.com", "example.com", "example.org", "example.net", "asdf"}
TYPO_DOMAINS = {"gmial.com": "gmail.com", "gamil.com": "gmail.com", "yaho.com": "yahoo.com",
                "hotmial.com": "hotmail.com", "outlok.com": "outlook.com"}
FREE_DOMAINS = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com", "icloud.com"}
JUNK_PHONES = {"0000000000", "1234567890", "12345", "1111111111", "5555555555"}
CONSENT_TRUE = {"yes", "y", "true", "1", "i agree", "agree", "opt-in", "opted in", "ok"}

_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF❤️]+"
)


def clean_name(value: Any) -> Optional[str]:
    """Trim, fix casing, strip emoji. Returns None for empty/test junk."""
    if value is None:
        return None
    s = _EMOJI_RE.sub("", str(value))
    s = unicodedata.normalize("NFKC", s).strip()
    if not s or s.lower() in {"test", "n/a", "none", "null", "-"}:
        return None
    if s.isupper() or s.islower():
        s = s.title()
    return s


def split_full_name(value: Any) -> tuple[Optional[str], Optional[str]]:
    s = clean_name(value)
    if not s:
        return None, None
    parts = s.split()
    if len(parts) == 1:
        return parts[0], None
    return parts[0], " ".join(parts[1:])


def clean_email(value: Any) -> tuple[Optional[str], list[str]]:
    """Returns (email, flags). Junk/typo domains are kept but flagged."""
    flags: list[str] = []
    if value is None or not str(value).strip():
        return None, ["email_missing"]
    s = str(value).strip().lower()
    domain = s.rsplit("@", 1)[-1] if "@" in s else ""
    if domain in TYPO_DOMAINS:
        flags.append(f"email_typo_domain:{domain}")
        s = s.rsplit("@", 1)[0] + "@" + TYPO_DOMAINS[domain]
        domain = s.rsplit("@", 1)[-1]
    try:
        result = validate_email(s, check_deliverability=False)
        s = result.normalized
    except EmailNotValidError:
        return None, ["email_invalid"]
    if domain in JUNK_EMAIL_DOMAINS or s.split("@")[0] in {"test", "asdf", "aaa"}:
        flags.append("email_junk")
    return s, flags


def clean_phone(value: Any, region: str = "US") -> tuple[Optional[str], list[str]]:
    """Normalize to E.164. Unparseable/junk -> (None, flags)."""
    if value is None or not str(value).strip():
        return None, ["phone_missing"]
    s = str(value).strip()
    digits = re.sub(r"\D", "", s)
    if digits in JUNK_PHONES or len(set(digits)) <= 1:
        return None, ["phone_junk"]
    try:
        parsed = phonenumbers.parse(s, region)
        if phonenumbers.is_possible_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164), []
        # Hackathon data uses Faker-style US numbers that fail strict
        # validity; possible-length 10-digit numbers still get normalized.
        if len(digits) == 10:
            return f"+1{digits}", ["phone_unverified"]
        return None, ["phone_unparseable"]
    except phonenumbers.NumberParseException:
        return None, ["phone_unparseable"]


def clean_date(value: Any) -> Optional[datetime]:
    """Epoch / ISO / MM-DD-YYYY / DD-Mon-YYYY / YYYY/MM/DD -> aware UTC."""
    if value is None or str(value).strip() == "":
        return None
    s = str(value).strip()
    if re.fullmatch(r"\d{9,13}", s):  # epoch seconds or millis
        ts = int(s)
        if ts > 10**12:
            ts //= 1000
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    try:
        dt = dateparser.parse(s)
    except (ValueError, OverflowError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def clean_consent(value: Any) -> bool:
    """Yes/yes/Y/TRUE/'I agree'/true -> True; missing/anything else -> False."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in CONSENT_TRUE


# Registry the LLM mapper composes from — names are part of the prompt.
TRANSFORMS = {
    "split_full_name": "value holds a full name; split into first_name + last_name",
    "first_name": "value is a first/given name",
    "last_name": "value is a last/family name",
    "email": "value is an email address",
    "phone": "value is a phone number",
    "campaign_id": "value identifies a marketing campaign",
    "consent": "value expresses opt-in/agreement",
    "created_at": "value is a date/timestamp of submission",
    "ignore": "value is irrelevant",
}
