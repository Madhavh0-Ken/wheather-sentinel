from __future__ import annotations

import hashlib
import json
from pathlib import Path

from storm_nowcast.models.schemas import ProvenanceRecord


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(path: Path, records: list[ProvenanceRecord]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "records": [record.model_dump(mode="json") for record in records],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def read_manifest(path: Path) -> list[ProvenanceRecord]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return [ProvenanceRecord.model_validate(item) for item in payload["records"]]

