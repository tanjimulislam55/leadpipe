# LEADPIPE DOCTOR
## ONLINE HACKATHON // ENGINEERING HANDOVER BRIEF

**The self-healing lead ingestion agent**
*Adapts to any lead source · Cleans every lead · Fixes itself when sources change*

| | |
|---|---|
| **Submission deadline** | Sunday · 6:00 AM |
| **Deliverable 1** | GitHub repository — code, README, generated data |
| **Deliverable 2** | Recorded demo video posted on Slack |
| **Hard rule** | Every tool 100% free & open source — no paid APIs, no closed models |
| **Prize** | Top 3 most useful builds — World Cup final seats at Sheraton |

> "Every marketing source speaks a different language.
> We build the translator that never breaks — and fixes itself when it does."

---

## 1 // The problem we are solving

US businesses spend heavily on ads to generate leads — Facebook Lead Ads, Instagram campaigns, Google Forms, landing pages — then lose those leads inside their own data plumbing. Six failures our product kills:

| Failure | Business damage |
|---|---|
| **Format chaos** | Facebook sends `full_name` in nested JSON; Instagram exports 'Full Name' in CSV; a Google Form asks 'What's your name?'; a landing page posts `fname` + `lname`. Engineers hand-write brittle mapping code per source, forever. |
| **Silent pipeline breaks** | Meta renames a field or a marketer edits a form — hardcoded pipelines crash or silently drop leads. Every lost lead was paid for with ad money. |
| **Dirty data downstream** | Phones in 7+ formats the dialer cannot call; `test@test.com` junk; missing consent flags = TCPA compliance risk in the US market. |
| **Cross-source duplicates** | Same person arrives from Facebook Monday and the landing page Wednesday. Two reps call them; attribution double-counts; budget goes to the wrong channel. |
| **Speed-to-lead dies** | Leads contacted within 5 minutes convert dramatically better. Manual weekly CSV cleanup turns hot leads cold. |
| **No lead prioritization** | A complete lead with valid mobile + corporate email deserves the first call. Without scoring, reps burn prime hours on junk. |

**Why an agent, not more rules:** Zapier-style tools and hardcoded ETL are rule-based — humans write the rules and the rules rot. LeadPipe Doctor is agent-based: it infers the mapping rules, verifies its own output, and rewrites the rules when reality changes. That is the innovation — **the LLM is structural, not decorative.**

---

## 2 // Project details — what to build

The product is an **agent pipeline**. A lead enters in any format; a clean, deduped, scored lead exits into one unified table. Build these capabilities in priority order.

| Priority | Feature | Requirement |
|---|---|---|
| **P0** | Auto schema profiling | Given sample rows/payloads from an unknown source, infer what each field represents. |
| **P0** | LLM schema mapping (RAG-grounded) | Map source fields to the canonical schema. Ground the LLM with retrieval over canonical schema docs + previously approved mappings so mapping improves over time. |
| **P0** | Generated cleaning code | Agent writes pandas transforms: phone to E.164, email validation, date parsing to UTC, consent normalization. Run in a restricted subprocess with a timeout. |
| **P0** | Validation contract | Every output row validated against a strict Pydantic model of the canonical schema. No invalid row ever reaches the database. |
| **P0** | Self-heal retry loop | On validation failure, feed the traceback back to code generation. Max 3 retries, then route the batch to a human-review queue. **THIS IS THE DEMO CENTERPIECE** — a schema change mid-run must recover with zero human touch. |
| **P1** | Mapping cache (fast path) | Approved mappings are stored and reused; the LLM runs only for new sources or detected drift. Right architecture + demo-latency insurance. |
| **P1** | Cross-source dedupe | Fuzzy match (name + phone + email) across sources; mark `status=duplicate`, keep the richest record. |
| **P1** | Lead quality scoring | 0–100 score. ML model (e.g. XGBoost) trained on synthetic labels; rule-based fallback acceptable if time runs out. |
| **P1** | Live dashboard | Leads flowing per source, clean rate, quality distribution, drift/heal events, human-review queue. |
| **P2** | Fine-tuned mapper model | Small fine-tune of the base model on ~200 synthetic mapping examples; log before/after accuracy. If time runs out, few-shot prompting with the base model is the fallback — document fine-tune as next step. |
| **P2** | Experiment tracking | Track mapping accuracy and validation pass rate per run (e.g. MLflow). |

> **Scope law:** ship every P0 before touching P1; ship P1 before P2. A pipeline that visibly fixes itself on camera beats five half-features.

---

## 3 // Canonical lead schema — the contract

Every source maps into this. **This schema is frozen** — do not change it mid-hackathon; everything downstream depends on it.

| Field | Type | Rule |
|---|---|---|
| `lead_id` | uuid | Generated on ingest |
| `first_name` / `last_name` | text | Split from `full_name` where needed; trim, fix casing, strip emoji |
| `email` | text | Validated; junk domains flagged |
| `phone_e164` | text | Normalized to E.164 (`+15551234567`); unparseable = flagged |
| `source` | enum | `facebook` \| `instagram` \| `google_form` \| `landing_page` |
| `campaign_id` | text | From payload (`campaign_id`, `Campaign`, `utm_campaign`...) |
| `consent` | bool | Normalize Yes/yes/Y/TRUE/'I agree'/true; missing = **false** (TCPA-safe default) |
| `created_at` | timestamptz | Parse epoch / ISO / MM-DD-YYYY / DD-Mon-YYYY, store UTC |
| `quality_score` | int 0–100 | From scorer |
| `status` | enum | `clean` \| `flagged` \| `duplicate` |
| `raw_payload` | jsonb | Original payload preserved — full auditability, nothing is ever lost |

---

## 4 // Tools we need to implement (all free & open source)

**Engineering freedom:** this stack is the recommended baseline, chosen for speed and zero cost. The team MAY replace or add any tool — on one condition: every tool used must be free & open source, and the README must state why it was chosen (one line per tool). If you swap a baseline tool, note what you swapped and why.

| Layer | Tool | Why this one |
|---|---|---|
| LLM serving | Ollama + Qwen 2.5 7B / Llama 3.1 8B | Local, free, OpenAI-compatible API; no keys, no cost, no rate limits |
| Agent orchestration | LangGraph | The profile→map→codegen→validate→retry loop is literally its core pattern |
| RAG / vectors | ChromaDB + nomic-embed-text | Zero-config embedded store for schema docs + mapping memory |
| Fine-tuning | Unsloth on free Colab T4 | Mapper fine-tune on ~200 examples in under 2 hours, runs in background |
| API / ingestion | FastAPI | Webhook endpoints + CSV folder watcher in one lightweight service |
| Cleaning libs | pandas · phonenumbers · email-validator · rapidfuzz | E.164 normalization, email checks, fuzzy dedupe — battle-tested |
| Validation | Pydantic | Hard schema contract; Great Expectations optional if time allows |
| Classic ML | XGBoost | Cheap, fast lead-quality classifier on synthetic labels |
| Database | PostgreSQL (DuckDB fallback) | Unified leads table with JSONB raw payload |
| Dashboard | Streamlit | Fastest path to a live demo UI in pure Python |
| MLOps | MLflow + Docker Compose | Run tracking + one-command reproducible stack for judges |
| Data generation | Faker | `generate_data.py` producing 100k+ leads matching the sample formats |
| Video recording | OBS Studio | Free, open source screen capture for the Slack demo video |

**Judging-criteria coverage:** base LLM (Qwen/Llama via Ollama) · RAG (Chroma) · agent framework (LangGraph) · fine-tune (Unsloth) · classic ML (XGBoost) · huge data (100k+ generated leads) · MLOps (MLflow, Docker Compose, reproducible run) · genuinely useful for engineers and the US CRM/marketing-automation market.

---

## 5 // Sample data pack (shipped with this brief)

Four sample source files + `DATA_README.txt` accompany this document. These define the exact formats the pipeline must handle. The team's `generate_data.py` must scale these same shapes (and the same mess) to 100k+ rows — the generated dataset ships inside the repo as a deliverable.

### Source 1 — `facebook_leads.jsonl` (Lead Ads webhook payload)

```json
{"entry":[{"id":"1234567890","time":1784208900,"changes":[{"field":"leadgen",
  "value":{"leadgen_id":"1745188...","campaign_id":"23851234567890789",
  "created_time":"2026-07-16T13:35:00+0000",
  "field_data":[{"name":"full_name","values":["Timothy Peterson"]},
    {"name":"email","values":["kingmichelle@example.org"]},
    {"name":"phone_number","values":["167-190-2294"]}]}}]}],"object":"page"}
```

### Source 2 — `instagram_export.csv` (Ads Manager style export)

```csv
Full Name,E-mail,Phone #,Campaign,Date Submitted,Consent?
Adam Bell,adam.bell@yahoo.com,688-937-3467,StoryAds_Q3,2026/07/04,Yes
Carrie Wolf,thompsonkendra@example.com,799-799-5527,Summer_Promo_IG,07/08/2026 03:39 AM,TRUE
```

### Source 3 — `google_form.csv` (Forms response export)

```csv
Timestamp,What's your name?,Best number to reach you,Your email address,How did you hear about us?,Do you agree to be contacted?
07/08/2026 19:36:00,Hannah Jenkins,702-838-5786,kimberly@gmial.com,Google,Yes
```

### Source 4 — `landing_page.jsonl` (flat JSON POST)

```json
{"fname":"Angela","lname":"Brown","email_addr":"warnerchristopher@example.com",
 "mobile":"591-803-3974","utm_campaign":"lp_july_sale","utm_source":"instagram",
 "opt_in":true,"submitted_at":"2026-07-05T03:08:00Z","lead_id":"998e9e90-..."}
```

### Intentional mess baked into all files (the agent must survive all of it)

| Mess type | Examples |
|---|---|
| Phones | 7+ formats: `+1 (555) 123-4567` · `555-123-4567` · `5551234567` · `1-555-...` · junk (`12345`, `N/A`, `000-000-0000`) |
| Emails | `test@test.com`, `asdf@asdf`, typo domains (`@gmial.com`) |
| Duplicates | ~25% of people appear in more than one source |
| Missing fields | Randomly dropped from Facebook `field_data` and landing page `mobile` |
| Dates | Epoch · ISO 8601 · MM/DD/YYYY hh:mm AM · DD-Mon-YYYY · YYYY/MM/DD |
| Consent | Yes / yes / Y / TRUE / 'I agree' / empty / boolean true-false |
| Names | ALL CAPS, emoji, empty rows, 'test' rows |

---

## 6 // Deliverables & demo video

### Deliverable 1 — GitHub repository must include

| Item | Requirement |
|---|---|
| Working code | Fresh-clone test passes: clone → `docker compose up` → replay → dashboard shows leads |
| README | Problem statement · quickstart (3 commands) · tool table with WHY per tool + license · data documentation · fine-tune notes · video link · limitations/next steps |
| Generated data | `data/` folder with the full generated datasets (the sample pack scaled to 100k+) |
| License proof | Tool/license table demonstrating the 100% open-source rule is met; zero API keys or paid references anywhere |
| Tagged release | `v1.0-hackathon` — post-deadline commits can't cause disputes |

### Deliverable 2 — demo video on Slack (max 4 minutes)

| Scene | On screen |
|---|---|
| **The problem** | 4 raw files side by side, same person, four formats. 'We pay for every lead, then lose it in the pipe.' |
| **One command up** | `docker compose up`. State the open-source rule is fully met. |
| **Leads flow live** | Dashboard fills; show one lead's journey raw payload → canonical row in Postgres. |
| **The kill shot** | Inject schema drift → red error → agent retries with traceback → green → flow resumes, zero human touch. Honesty line: sources simulated in authentic payload formats; production points the real webhook here. |
| **Dedupe + scoring** | Same person from two sources caught & merged; score 92 vs score 11. |
| **The stack** | MLflow accuracy, LangGraph graph, repo tree. 'Built for the hackathon. 100% free & open source.' |

**Recording rules:** record from an already-tested run — never improvise the drift demo live. OBS Studio. Slack message = team name + repo URL + video + 2-line pitch. **Submit everything by Sunday 5:30 AM** — 30-minute buffer against upload failures.

---

> **Final word:** One thing done impressively — a pipeline that visibly fixes itself on camera — beats five things half-done. Protect the kill shot. Ship the video early. Bismillah — go win those Sheraton seats.
