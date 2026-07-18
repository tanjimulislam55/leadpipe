"""Generate 100k+ synthetic leads in the four source formats from the brief,
with the intentional mess baked in: mixed phone/date/consent formats, junk
emails and typo domains, ~25% cross-source duplicates, missing fields,
ALL-CAPS/emoji/test names.

Usage:
    python generate_data.py                  # 100k rows into data/generated/
    python generate_data.py --rows 500 --out data/samples   # small sample pack
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from faker import Faker

fake = Faker("en_US")

CAMPAIGNS = {
    "facebook": ["23851234567890789", "23851234567890111", "23851234567890222"],
    "instagram": ["StoryAds_Q3", "Summer_Promo_IG", "Reels_July_Blast"],
    "google_form": ["Google", "Friend", "Instagram", "Radio", "Other"],
    "landing_page": ["lp_july_sale", "lp_summer_promo", "lp_worldcup_special"],
}
EMOJIS = ["😀", "🔥", "❤️", "✨", "🙏"]
JUNK_PHONES = ["12345", "N/A", "000-000-0000", "1111111111"]
JUNK_EMAILS = ["test@test.com", "asdf@asdf", "aaa@aaa.aaa"]
TYPO_DOMAINS = ["gmial.com", "gamil.com", "yaho.com", "hotmial.com"]
CONSENT_YES = ["Yes", "yes", "Y", "TRUE", "I agree", "true"]
CONSENT_NO = ["No", "no", "FALSE", "", "false"]


def make_person(rng: random.Random) -> dict:
    first, last = fake.first_name(), fake.last_name()
    return {
        "first": first,
        "last": last,
        "email": f"{first.lower()}.{last.lower()}@{rng.choice(['gmail.com', 'yahoo.com', 'outlook.com', 'acme-corp.com', 'bigco.io'])}",
        "phone_digits": f"{rng.randint(201, 989)}{rng.randint(200, 999)}{rng.randint(1000, 9999)}",
        "when": datetime(2026, 7, rng.randint(1, 17), rng.randint(0, 23),
                         rng.randint(0, 59), rng.randint(0, 59), tzinfo=timezone.utc),
    }


def mess_name(p: dict, rng: random.Random) -> str:
    name = f"{p['first']} {p['last']}"
    r = rng.random()
    if r < 0.08:
        return name.upper()
    if r < 0.11:
        return name + rng.choice(EMOJIS)
    if r < 0.125:
        return name.lower()
    if r < 0.135:
        return "test"
    if r < 0.14:
        return ""
    return name


def mess_email(p: dict, rng: random.Random) -> str:
    r = rng.random()
    if r < 0.03:
        return rng.choice(JUNK_EMAILS)
    if r < 0.06:
        local = p["email"].split("@")[0]
        return f"{local}@{rng.choice(TYPO_DOMAINS)}"
    if r < 0.07:
        return ""
    return p["email"]


def mess_phone(p: dict, rng: random.Random) -> str:
    d = p["phone_digits"]
    r = rng.random()
    if r < 0.04:
        return rng.choice(JUNK_PHONES)
    if r < 0.06:
        return ""
    style = rng.randrange(6)
    if style == 0:
        return f"+1 ({d[:3]}) {d[3:6]}-{d[6:]}"
    if style == 1:
        return f"{d[:3]}-{d[3:6]}-{d[6:]}"
    if style == 2:
        return d
    if style == 3:
        return f"1-{d[:3]}-{d[3:6]}-{d[6:]}"
    if style == 4:
        return f"({d[:3]}) {d[3:6]} {d[6:]}"
    return f"{d[:3]}.{d[3:6]}.{d[6:]}"


def fmt_date(dt: datetime, style: str) -> str:
    if style == "epoch":
        return str(int(dt.timestamp()))
    if style == "iso":
        return dt.strftime("%Y-%m-%dT%H:%M:%S+0000")
    if style == "us_ampm":
        return dt.strftime("%m/%d/%Y %I:%M %p")
    if style == "dd_mon":
        return dt.strftime("%d-%b-%Y")
    if style == "slash_ymd":
        return dt.strftime("%Y/%m/%d")
    return dt.strftime("%m/%d/%Y %H:%M:%S")


def facebook_row(p: dict, rng: random.Random, drift: bool = False) -> str:
    field_data = []
    phone_key = "contact_phone" if drift else "phone_number"
    fields = [("full_name", mess_name(p, rng)), ("email", mess_email(p, rng)),
              (phone_key, mess_phone(p, rng))]
    for name, value in fields:
        if rng.random() < 0.05:  # randomly dropped fields
            continue
        field_data.append({"name": name, "values": [value]})
    payload = {
        "entry": [{
            "id": str(rng.randrange(10**9, 10**10)),
            "time": int(p["when"].timestamp()),
            "changes": [{
                "field": "leadgen",
                "value": {
                    "leadgen_id": str(rng.randrange(10**15, 10**16)),
                    "campaign_id": rng.choice(CAMPAIGNS["facebook"]),
                    "created_time": fmt_date(p["when"], "iso"),
                    "field_data": field_data,
                },
            }],
        }],
        "object": "page",
    }
    return json.dumps(payload)


def instagram_row(p: dict, rng: random.Random) -> list[str]:
    date_style = rng.choice(["slash_ymd", "us_ampm"])
    return [mess_name(p, rng), mess_email(p, rng), mess_phone(p, rng),
            rng.choice(CAMPAIGNS["instagram"]), fmt_date(p["when"], date_style),
            rng.choice(CONSENT_YES + CONSENT_NO[:2])]


def google_form_row(p: dict, rng: random.Random) -> list[str]:
    return [fmt_date(p["when"], rng.choice(["us_full", "dd_mon"])),
            mess_name(p, rng), mess_phone(p, rng), mess_email(p, rng),
            rng.choice(CAMPAIGNS["google_form"]),
            rng.choice(CONSENT_YES + [""])]


def landing_page_row(p: dict, rng: random.Random) -> str:
    payload = {
        "fname": p["first"], "lname": p["last"],
        "email_addr": mess_email(p, rng),
        "utm_campaign": rng.choice(CAMPAIGNS["landing_page"]),
        "utm_source": rng.choice(["instagram", "facebook", "google"]),
        "opt_in": rng.choice([True, True, False]),
        "submitted_at": p["when"].strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lead_id": str(uuid.UUID(int=rng.getrandbits(128))),
    }
    if rng.random() >= 0.06:  # mobile randomly dropped
        payload["mobile"] = mess_phone(p, rng)
    return json.dumps(payload)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=100_000, help="total rows across all sources")
    ap.add_argument("--out", default="data/generated")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    Faker.seed(args.seed)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    n_people = int(args.rows / 1.25)  # ~25% duplicates across sources
    sources = ["facebook", "instagram", "google_form", "landing_page"]

    fb = open(out / "facebook_leads.jsonl", "w")
    lp = open(out / "landing_page.jsonl", "w")
    ig_f = open(out / "instagram_export.csv", "w", newline="")
    gf_f = open(out / "google_form.csv", "w", newline="")
    ig = csv.writer(ig_f)
    gf = csv.writer(gf_f)
    ig.writerow(["Full Name", "E-mail", "Phone #", "Campaign", "Date Submitted", "Consent?"])
    gf.writerow(["Timestamp", "What's your name?", "Best number to reach you",
                 "Your email address", "How did you hear about us?",
                 "Do you agree to be contacted?"])

    total = 0
    for _ in range(n_people):
        p = make_person(rng)
        appearances = [rng.choice(sources)]
        if rng.random() < 0.25:  # cross-source duplicate
            appearances.append(rng.choice([s for s in sources if s != appearances[0]]))
        for src in appearances:
            if src == "facebook":
                fb.write(facebook_row(p, rng) + "\n")
            elif src == "instagram":
                ig.writerow(instagram_row(p, rng))
            elif src == "google_form":
                gf.writerow(google_form_row(p, rng))
            else:
                lp.write(landing_page_row(p, rng) + "\n")
            total += 1

    for f in (fb, lp, ig_f, gf_f):
        f.close()
    print(f"people: {n_people}  rows written: {total}  ->  {out}/")


if __name__ == "__main__":
    main()
