"""Cross-source dedupe: fuzzy match on name + phone + email.

Leads sharing a normalized phone or email are grouped (union-find), and a
rapidfuzz name-similarity check guards against household/shared-line false
positives. The richest record (highest quality score) survives; the rest are
marked status=duplicate. Nothing is deleted — raw payloads stay auditable.

Usage: python dedupe.py
"""
from __future__ import annotations

import time

from rapidfuzz import fuzz

from leadpipe import db

NAME_SIMILARITY_MIN = 55  # loose: same phone+different-looking name still often same person


class UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def main() -> None:
    t0 = time.time()
    con = db.connect()
    rows = con.execute("""
        SELECT lead_id, coalesce(first_name,'') || ' ' || coalesce(last_name,'') AS name,
               phone_e164, email, source, quality_score
        FROM leads WHERE status != 'duplicate'
    """).fetchall()
    n = len(rows)
    uf = UnionFind(n)

    def link_by(key_idx: int) -> None:
        buckets: dict[str, int] = {}
        for i, row in enumerate(rows):
            key = row[key_idx]
            if not key:
                continue
            if key in buckets:
                j = buckets[key]
                # fuzzy name confirmation before merging
                if fuzz.token_sort_ratio(rows[i][1], rows[j][1]) >= NAME_SIMILARITY_MIN \
                        or not rows[i][1].strip() or not rows[j][1].strip():
                    uf.union(j, i)
            else:
                buckets[key] = i

    link_by(2)  # phone_e164
    link_by(3)  # email

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(uf.find(i), []).append(i)

    dupes: list[str] = []
    cross_source = 0
    for members in groups.values():
        if len(members) < 2:
            continue
        # richest record survives: highest quality score wins
        members.sort(key=lambda i: rows[i][5], reverse=True)
        if len({rows[i][4] for i in members}) > 1:
            cross_source += 1
        dupes.extend(rows[i][0] for i in members[1:])

    if dupes:
        con.executemany("UPDATE leads SET status='duplicate' WHERE lead_id = ?",
                        [(d,) for d in dupes])
    print(f"scanned {n} leads in {time.time()-t0:.1f}s: "
          f"{len(dupes)} duplicates marked "
          f"({cross_source} cross-source groups); richest record kept per group")


if __name__ == "__main__":
    main()
