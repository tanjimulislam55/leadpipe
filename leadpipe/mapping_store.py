"""Mapping cache (fast path) + ChromaDB RAG memory.

Approved mappings live in two places:
- data/mappings.json — exact-match cache keyed by source name. The LLM only
  runs for unknown sources or after drift invalidates the cache.
- ChromaDB — per-field examples embedded with nomic-embed-text (via Ollama).
  When mapping a NEW source, similar previously-approved fields are retrieved
  and grounded into the prompt, so mapping improves over time.
"""
from __future__ import annotations

import json
from pathlib import Path

import requests

from .llm_mapper import OLLAMA_URL

CACHE_PATH = Path("data/mappings.json")
CHROMA_PATH = "data/chroma"
EMBED_MODEL = "nomic-embed-text"


def _embed(texts: list[str]) -> list[list[float]]:
    out = []
    for t in texts:
        resp = requests.post(f"{OLLAMA_URL}/api/embeddings",
                             json={"model": EMBED_MODEL, "prompt": t}, timeout=60)
        resp.raise_for_status()
        out.append(resp.json()["embedding"])
    return out


class MappingStore:
    def __init__(self, cache_path: Path = CACHE_PATH):
        self.cache_path = cache_path
        self.cache: dict[str, dict[str, str]] = {}
        if cache_path.exists():
            self.cache = json.loads(cache_path.read_text())
        self._collection = None

    # -- exact-match cache ------------------------------------------------
    def get(self, source_name: str) -> dict[str, str] | None:
        return self.cache.get(source_name)

    def invalidate(self, source_name: str) -> None:
        self.cache.pop(source_name, None)
        self._save()

    def approve(self, source_name: str, mapping: dict[str, str],
                profile: dict) -> None:
        """Persist to cache AND remember per-field examples in Chroma."""
        self.cache[source_name] = mapping
        self._save()
        self._remember_fields(source_name, mapping, profile)

    def _save(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self.cache, indent=2))

    # -- RAG memory -------------------------------------------------------
    def _get_collection(self):
        if self._collection is None:
            import chromadb
            client = chromadb.PersistentClient(path=CHROMA_PATH)
            self._collection = client.get_or_create_collection("field_mappings")
        return self._collection

    def _field_doc(self, field: str, samples: list) -> str:
        return f"source field '{field}' with sample values {samples[:3]}"

    def _remember_fields(self, source_name: str, mapping: dict[str, str],
                         profile: dict) -> None:
        docs, ids, metas = [], [], []
        for field, transform in mapping.items():
            if transform == "ignore":
                continue
            docs.append(self._field_doc(field, profile.get(field, {}).get("samples", [])))
            ids.append(f"{source_name}::{field}")
            metas.append({"source": source_name, "field": field, "transform": transform})
        if not docs:
            return
        try:
            self._get_collection().upsert(
                ids=ids, documents=docs, embeddings=_embed(docs), metadatas=metas)
        except Exception as e:  # RAG memory is an enhancement, never a blocker
            print(f"[rag] warning: could not store mappings: {e}")

    def similar_examples(self, profile: dict, k: int = 6) -> list[str]:
        """Retrieve previously approved mappings for fields similar to this
        profile — returned as prompt-ready lines."""
        try:
            col = self._get_collection()
            if col.count() == 0:
                return []
            query = self._field_doc("unknown", []) + " " + json.dumps(
                {f: p["samples"][:2] for f, p in list(profile.items())[:12]})
            res = col.query(query_embeddings=_embed([query]),
                            n_results=min(k, col.count()))
            lines = []
            for doc, meta in zip(res["documents"][0], res["metadatas"][0]):
                lines.append(f"- {doc} was approved as transform '{meta['transform']}'")
            return lines
        except Exception as e:
            print(f"[rag] warning: retrieval failed: {e}")
            return []
