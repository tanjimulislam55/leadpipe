"""LLM schema mapping via Ollama.

The LLM's ONLY job: look at a profile of an unknown source (field names +
sample values) and return a JSON mapping {source_field: transform_name}.
It never writes free-form code — it composes the battle-tested transforms
in cleaners.TRANSFORMS. Ollama's format="json" mode guarantees parseable
output; validate_mapping() guarantees semantic sanity; the retry loop
handles the rest.
"""
from __future__ import annotations

import json
import os
from collections import Counter
from typing import Optional

import requests

from .cleaners import TRANSFORMS
from .schema import SCHEMA_DOC

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("LEADPIPE_MODEL", "qwen2.5:7b")
# Optional second model to try on request errors; defaults to retrying the
# primary (set e.g. LEADPIPE_FALLBACK_MODEL=llama3:latest if you have one pulled).
FALLBACK_MODEL = os.environ.get("LEADPIPE_FALLBACK_MODEL", MODEL)


def profile_source(records: list[dict], sample_size: int = 12) -> dict:
    """Field names, example values, and fill rates — the LLM's evidence."""
    fields: Counter = Counter()
    samples: dict[str, list] = {}
    for rec in records[:500]:
        for k, v in rec.items():
            fields[k] += 1
            if v not in (None, "") and len(samples.setdefault(k, [])) < 4:
                samples[k].append(str(v)[:60])
    n = min(len(records), 500)
    return {
        field: {
            "fill_rate": round(count / n, 2),
            "samples": samples.get(field, []),
        }
        for field, count in fields.items()
    }


class MappingRejected(Exception):
    """LLM output failed semantic validation. Message explains why —
    it gets appended to the retry prompt."""


def validate_mapping(mapping: dict, profile: dict) -> dict[str, str]:
    if not isinstance(mapping, dict) or not mapping:
        raise MappingRejected("output must be a non-empty JSON object")
    clean: dict[str, str] = {}
    for field, transform in mapping.items():
        if field not in profile:
            raise MappingRejected(
                f"mapped field {field!r} does not exist in the source data; "
                f"real fields are {sorted(profile)}")
        if transform not in TRANSFORMS:
            # 7B models love inventing transforms like 'source' for utm_source.
            # Coerce to ignore; the required-coverage checks below still gate.
            transform = "ignore"
        clean[field] = transform
    targets = set(clean.values())
    if not ({"email", "phone"} & targets):
        raise MappingRejected("mapping must identify at least an email or phone field")
    if not ({"split_full_name", "first_name"} & targets):
        raise MappingRejected("mapping must identify a name field")
    for field in profile:
        clean.setdefault(field, "ignore")
    return clean


def _build_prompt(source_name: str, profile: dict, rag_examples: list[str],
                  feedback: Optional[str] = None) -> str:
    transforms_doc = "\n".join(f"- {name}: {desc}" for name, desc in TRANSFORMS.items())
    parts = [
        "You map raw marketing-lead fields to a canonical CRM schema.",
        f"\n## Canonical schema\n{SCHEMA_DOC}",
        f"\n## Allowed transforms (the ONLY legal values)\n{transforms_doc}",
    ]
    if rag_examples:
        parts.append("\n## Previously approved mappings for similar fields\n"
                     + "\n".join(rag_examples))
    parts.append(f"\n## Source to map: {source_name}\nField profile (name, fill rate, sample values):\n"
                 + json.dumps(profile, indent=1))
    if feedback:
        parts.append(f"\n## Your previous attempt FAILED. Fix this:\n{feedback}")
    parts.append(
        "\nReturn ONLY a JSON object mapping every source field name to one transform, e.g."
        ' {"Full Name": "split_full_name", "E-mail": "email", "extra_col": "ignore"}.'
        " Use \"ignore\" for irrelevant fields. Do not invent field names.")
    return "\n".join(parts)


def _call_ollama(prompt: str, model: str) -> dict:
    resp = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "format": "json",
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 600},
        },
        timeout=180,
    )
    resp.raise_for_status()
    return json.loads(resp.json()["message"]["content"])


def infer_mapping(source_name: str, profile: dict, rag_examples: list[str],
                  feedback: Optional[str] = None, attempts: int = 3) -> dict[str, str]:
    """Profile -> validated mapping, retrying with error feedback in-prompt."""
    model = MODEL
    last_err: Exception = MappingRejected("no attempts made")
    for attempt in range(attempts):
        prompt = _build_prompt(source_name, profile, rag_examples, feedback)
        try:
            raw = _call_ollama(prompt, model)
            return validate_mapping(raw, profile)
        except MappingRejected as e:
            feedback = str(e)
            last_err = e
        except (requests.RequestException, json.JSONDecodeError, KeyError) as e:
            last_err = e
            if model == MODEL:  # model missing/unresponsive -> fallback model
                model = FALLBACK_MODEL
    raise MappingRejected(f"LLM mapping failed after {attempts} attempts: {last_err}")
