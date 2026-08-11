"""
Test infrastructure only -- not FootCap domain logic.

Mechanical loading and validation helpers for the JSON Schema contracts
under packages/contracts/schemas/. Used by the Phase 0.4 test suite to
load a named schema, resolve its local and cross-file $refs (e.g.
"definitions.schema.json#/$defs/Identifier"), and build a real
jsonschema Draft202012Validator against it.

This module must never embed or duplicate contract definitions; it only
locates and loads the files that packages/contracts/schemas/ already
authors, per packages/contracts/README.md.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012


def repo_root() -> Path:
    """Locate the repository root by walking up from this file until a
    packages/contracts/schemas directory is found."""
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "packages" / "contracts" / "schemas").is_dir():
            return candidate
    raise RuntimeError(
        "Could not locate the repository root: no ancestor of "
        f"{__file__} contains packages/contracts/schemas/."
    )


def schemas_dir() -> Path:
    """The single source of truth for shared contracts (packages/contracts/README.md)."""
    return repo_root() / "packages" / "contracts" / "schemas"


@lru_cache(maxsize=None)
def _all_schema_documents() -> dict[str, dict]:
    """filename -> parsed schema dict, for every *.schema.json file in schemas_dir()."""
    documents = {}
    for path in sorted(schemas_dir().glob("*.schema.json")):
        documents[path.name] = json.loads(path.read_text(encoding="utf-8"))
    return documents


@lru_cache(maxsize=None)
def _registry() -> Registry:
    """A referencing.Registry containing every schema file, keyed by its
    own $id, so that both same-file ('#/$defs/...') and cross-file
    ('definitions.schema.json#/$defs/...') $refs resolve."""
    resources = [
        (document["$id"], Resource.from_contents(document, default_specification=DRAFT202012))
        for document in _all_schema_documents().values()
    ]
    return Registry().with_resources(resources)


def load_schema(filename: str) -> dict:
    """Return the parsed schema dict for e.g. 'prediction.schema.json'."""
    documents = _all_schema_documents()
    if filename not in documents:
        available = ", ".join(sorted(documents))
        raise FileNotFoundError(f"No such contract schema '{filename}'. Available: {available}")
    return documents[filename]


def validator_for(filename: str) -> Draft202012Validator:
    """A Draft202012Validator for the named schema, with every sibling
    schema under packages/contracts/schemas/ registered so its local and
    cross-file $refs resolve."""
    return Draft202012Validator(load_schema(filename), registry=_registry())
