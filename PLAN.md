# LeadPipe Doctor — Build Plan & Progress Tracker

> Deadline: **Sunday 6:00 AM** (submit by 5:30 AM). Build started Saturday ~22:45.
> Time budget: **~7 hours.** Scope law: P0 → P1 → P2. Protect the kill shot (self-heal demo).

## Timeline at a glance

| Phase | Target done by | What | Status |
|---|---|---|---|
| 1. Skeleton pipeline | ~23:45 | End-to-end flow, no LLM yet | ✅ done 23:20 |
| 2. LLM brain | ~01:15 | Ollama mapping + cache + RAG | ✅ done 23:20 |
| 3. Kill shot | ~02:45 | Self-heal loop + drift demo | ✅ done 23:21 (healed attempt 1) |
| 4. Garnish (P1) | ~03:45 | Dedupe, scoring, dashboard polish | ✅ done 23:30 |
| 5. Ship | 05:30 HARD STOP | README, compose, video, tag, Slack | ⬜ |

---

## Phase 1 — Skeleton first, LLM last (target ~23:45)

Prove the plumbing end-to-end with hardcoded mappings. Demoable within the hour.

- [x] Project structure + venv + dependencies
- [x] `leadpipe/schema.py` — canonical Pydantic model (the frozen contract)
- [x] `leadpipe/cleaners.py` — pre-built cleaning functions: phone→E.164, email validation, date→UTC, consent normalization, name split/casing/emoji-strip
- [x] `generate_data.py` — Faker, 100k+ leads across all 4 source formats, with intentional mess (junk phones, typo emails, ~25% cross-source duplicates, mixed date formats, consent variants, ALL-CAPS/emoji names)
- [x] Sample files recreated in `data/samples/` (4 formats from the brief)
- [x] `leadpipe/db.py` — DuckDB unified leads table (raw_payload preserved as JSON)
- [x] `leadpipe/pipeline.py` — ingest → map (hardcoded) → clean → Pydantic validate → store
- [x] `dashboard.py` — Streamlit: leads per source, clean rate, table view
- [x] ✅ Milestone HIT 23:20: 100,154 rows → DuckDB in 193s, 84.6% clean, 0 validation failures; dashboard live on :8501
- [x] Bonus: rule-based quality scorer (`leadpipe/scorer.py`) landed early

## Phase 2 — Swap in the brain (target ~01:15)

LLM infers the mapping; pre-written cleaners do the work. LLM outputs **JSON mapping only**, never freestyle code (7B-model reliability).

- [x] `profile_source()` — column names + sample values + fill rates per unknown source
- [x] `leadpipe/llm_mapper.py` — Ollama (qwen2.5, llama3 fallback) returns JSON mapping via format="json"; semantic validation + in-prompt retry
- [x] Mapping cache — `data/mappings.json`; LLM only runs for unknown sources or drift
- [x] ChromaDB RAG — approved field mappings embedded (nomic-embed-text), retrieved into mapping prompt (judging checkbox: RAG ✓)
- [x] Hardcoded mappings demoted to `--no-llm` debug flag — pipeline cold-starts any source via LLM
- [x] ✅ Milestone HIT 23:20: cache wiped → LLM inferred all 4 mappings correctly (even improved one: "How did you hear about us?" → ignore), 16k rows, 0 failures
- Fix log: 7B model kept inventing transform 'source' for utm_source → unknown transforms now coerced to 'ignore' (coverage checks still gate); review_queue needed json.dumps not str(dict)

## Phase 3 — The kill shot (target ~02:45) ⭐ DEMO CENTERPIECE

- [x] Validation-failure loop (`leadpipe/doctor.py`): drift report → LLM → corrected mapping → retry (max 3) → human-review queue on final failure
- [x] Drift detection: mapped fields missing >80% of batch OR >50% rows invalid → MappingDriftError with diagnostic report (that report IS the LLM feedback)
- [x] `inject_drift.py` — renames `phone_number`→`contact_phone`, `full_name`→`applicant_name` from row N on (has --restore)
- [x] Heal events logged (heal_events table) + dashboard timeline (🔴 drift → 🟡 retry → 🟢 healed)
- [x] ✅ Milestone HIT 23:21: drift at row 2000 mid-run → detected → healed on **attempt 1**, zero human touch, all rows stored
- [x] ✅ 3 clean rehearsals in a row — healed on attempt 1 every time (23:21, 23:52, 00:15)

## Phase 4 — P1 garnish, strictly timeboxed (target ~03:45)

- [x] Cross-source dedupe (`dedupe.py`) — union-find on shared phone/email + rapidfuzz name confirmation, `status=duplicate`, richest record kept; 40k leads in 4.5s
- [x] Lead quality scoring — rule-based 0–100 (`leadpipe/scorer.py`); XGBoost documented as next step
- [x] Dashboard panels: quality distribution, drift/heal event feed, human-review queue, dedupe count
- [ ] ✅ Milestone: same person from 2 sources merged on dashboard; score 90+ vs junk score visible

## Phase 5 — Ship (start no later than 03:45, submit 05:30)

- [x] `docker-compose.yml` — ollama + model-init + pipeline + dashboard (DuckDB = no DB container); local venv path documented as tested alternative
- [x] README — problem, 3-command quickstart, tool table (WHY + license per tool), data docs, fine-tune notes, limitations/next steps, video-link placeholder
- [x] Generated data committed to `data/` (100,154 rows, 32MB, clean/undrifted version)
- [x] Git init, commit `28d4317`, tag `v1.0-hackathon`
- [x] `DEMO_SCRIPT.md` — scene-by-scene script with exact commands + Slack message template
- [x] Docker compose build verified (app image builds; dashboard serves HTTP 200 in container)
- [x] GitHub pushed: github.com/tanjimulislam55/leadpipe (main + v1.0-hackathon tag)
- [ ] **USER: record video** (OBS, max 4 min) — follow DEMO_SCRIPT.md, reset commands included
- [ ] **USER: update README video link + Slack post** — template at bottom of DEMO_SCRIPT.md — **by 5:30 AM**

## Explicitly CUT (README "next steps" section)

- ❌ Unsloth fine-tune → documented as next step (brief allows few-shot fallback)
- ❌ MLflow → simple run-metrics JSON log instead
- ❌ XGBoost → rule-based scorer (brief explicitly allows)
- ❌ Postgres → DuckDB (brief explicitly allows)
- ❌ FastAPI webhooks → file replay simulates sources (honesty line in video covers this)

## Decisions log

- 22:42 — Ollama installed, llama3:8b available locally; qwen2.5:7b pulling in background (better JSON output; llama3 is the fallback)
- 22:45 — DuckDB over Postgres and file-replay over FastAPI: fewer moving parts, same demo value
