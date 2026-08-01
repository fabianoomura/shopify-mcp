from __future__ import annotations

import hashlib
import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class MutationAuditor:
    """Auditoria append-only, deliberadamente sem valores de negócio ou PII."""

    def __init__(self, path: Path | None):
        self.path = path
        self._lock = threading.Lock()

    @staticmethod
    def _target_hash(arguments: dict[str, Any]) -> str | None:
        target = arguments.get("id")
        if not isinstance(target, str) or not target:
            return None
        return hashlib.sha256(target.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _summary(arguments: dict[str, Any]) -> dict[str, Any]:
        summary: dict[str, Any] = {"fields": sorted(k for k in arguments if k != "confirm")}
        tags = arguments.get("tags")
        if isinstance(tags, list):
            summary["tagCount"] = len(tags)
        return summary

    def record(self, *, tool: str, arguments: dict[str, Any], outcome: str, error_type: str | None = None) -> None:
        if self.path is None:
            return
        event = {
            "timestamp": datetime.now(UTC).isoformat(),
            "tool": tool,
            "outcome": outcome,
            "targetHash": self._target_hash(arguments),
            "argumentSummary": self._summary(arguments),
        }
        if error_type:
            event["errorType"] = error_type
        line = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self.path.open("a", encoding="utf-8", newline="") as stream:
            stream.write(line)

