"""Local durable result store keyed by idempotency key (stand-in for Cosmos DB / Azure SQL)."""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import REPO_ROOT


class ResultStore:
    def __init__(self, root: Path | None = None):
        self.root = Path(root or os.environ.get("SIV_RESULTS_DIR", REPO_ROOT / ".runs" / "results"))
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def get(self, key: str) -> dict | None:
        p = self._path(key)
        return json.loads(p.read_text()) if p.exists() else None

    def put_if_absent(self, key: str, record: dict) -> bool:
        """Exclusive create (O_EXCL). Returns False if a record already exists (duplicate delivery)."""
        try:
            with self._path(key).open("x") as f:
                json.dump(record, f, indent=2)
            return True
        except FileExistsError:
            return False

    def count(self) -> int:
        return len(list(self.root.glob("*.json")))
