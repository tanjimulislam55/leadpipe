"""The Doctor: mapping resolution + the self-heal retry loop.

Flow per batch:
  cached mapping (fast path, no LLM)
    └─ process_batch OK        -> store leads
    └─ MappingDriftError       -> the heal loop:
         attempt 1..3: feed the drift report back to the LLM,
                       get a corrected mapping, re-process
         success  -> log 'healed', approve new mapping (cache + RAG)
         3 fails  -> batch to human-review queue, log 'human_review'

Unknown source (no cache) is just the degenerate case: infer first, then run.
"""
from __future__ import annotations

import duckdb

from . import db
from .llm_mapper import MappingRejected, infer_mapping, profile_source
from .mapping_store import MappingStore
from .pipeline import MappingDriftError, process_batch
from .schema import CanonicalLead, Source

MAX_HEAL_ATTEMPTS = 3


class Doctor:
    def __init__(self, con: duckdb.DuckDBPyConnection, store: MappingStore,
                 verbose: bool = True):
        self.con = con
        self.store = store
        self.verbose = verbose

    def _say(self, msg: str) -> None:
        if self.verbose:
            print(msg)

    def _infer(self, source_name: str, records: list[dict],
               feedback: str | None = None) -> dict[str, str]:
        profile = profile_source(records)
        rag = self.store.similar_examples(profile)
        if rag:
            self._say(f"  [rag] grounding with {len(rag)} prior field mappings")
        mapping = infer_mapping(source_name, profile, rag, feedback=feedback)
        return mapping

    def process(self, source: Source, records: list[dict]
                ) -> tuple[list[CanonicalLead], list[dict]]:
        """Process one batch, self-healing on drift. Returns (leads, failures).
        Raises nothing on drift — after MAX_HEAL_ATTEMPTS the batch goes to
        the human-review queue and ([], records) is returned."""
        name = source.value
        mapping = self.store.get(name)

        if mapping is None:  # cold start: unknown source
            self._say(f"  [llm] no cached mapping for '{name}' — inferring...")
            try:
                mapping = self._infer(name, records)
            except MappingRejected as e:
                return self._give_up(name, records, f"cold-start mapping failed: {e}")
            self.store.approve(name, mapping, profile_source(records))
            db.log_heal_event(self.con, name, "mapping_learned", detail=str(mapping))
            self._say(f"  [llm] learned mapping: {mapping}")

        try:
            return process_batch(records, mapping, source)
        except MappingDriftError as e:
            report = str(e)
            db.log_heal_event(self.con, name, "drift_detected", detail=report)
            self._say(f"  🔴 [drift] {name}: mapping no longer fits the data")
            self.store.invalidate(name)

        # ---- the heal loop ------------------------------------------------
        feedback = report
        for attempt in range(1, MAX_HEAL_ATTEMPTS + 1):
            db.log_heal_event(self.con, name, "retry", attempt=attempt)
            self._say(f"  🟡 [heal] attempt {attempt}/{MAX_HEAL_ATTEMPTS}: "
                      f"re-mapping '{name}' with failure report in-prompt")
            try:
                mapping = self._infer(name, records, feedback=feedback)
                leads, failures = process_batch(records, mapping, source)
            except MappingDriftError as e:
                feedback = str(e)
                continue
            except MappingRejected as e:
                feedback = str(e)
                continue
            self.store.approve(name, mapping, profile_source(records))
            db.log_heal_event(self.con, name, "healed", attempt=attempt,
                              detail=str(mapping))
            self._say(f"  🟢 [healed] '{name}' recovered on attempt {attempt}, "
                      f"zero human touch. New mapping: {mapping}")
            return leads, failures

        return self._give_up(name, records,
                             f"unhealed after {MAX_HEAL_ATTEMPTS} attempts: {feedback}")

    def _give_up(self, name: str, records: list[dict], reason: str
                 ) -> tuple[list[CanonicalLead], list[dict]]:
        db.log_heal_event(self.con, name, "human_review", detail=reason)
        for rec in records[:1000]:
            db.queue_for_review(self.con, name, reason[:200], rec)
        self._say(f"  🟠 [review] '{name}' batch routed to human-review queue")
        return [], records
