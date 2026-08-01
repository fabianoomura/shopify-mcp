from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any


class ConfirmationError(ValueError):
    pass


@dataclass(slots=True)
class Proposal:
    tool: str
    arguments_digest: str
    expires_at: float


class ConfirmationManager:
    """Tokens opacos, de uso único e ligados exatamente à mutação preparada."""

    def __init__(self, ttl_seconds: int = 600, secret: bytes | None = None, max_pending: int = 10000):
        if not 30 <= ttl_seconds <= 3600:
            raise ValueError("TTL de confirmação deve estar entre 30 e 3600 segundos")
        self.ttl_seconds = ttl_seconds
        if not 1 <= max_pending <= 100000:
            raise ValueError("max_pending deve estar entre 1 e 100000")
        self.max_pending = max_pending
        self._secret = secret or secrets.token_bytes(32)
        self._pending: dict[str, Proposal] = {}
        self._lock = threading.Lock()

    def _prune_expired(self, now: float) -> None:
        expired = [nonce for nonce, proposal in self._pending.items() if now > proposal.expires_at]
        for nonce in expired:
            self._pending.pop(nonce, None)

    @staticmethod
    def _digest(arguments: dict[str, Any]) -> str:
        canonical = json.dumps(arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def issue(self, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        nonce = secrets.token_urlsafe(24)
        signature = hmac.new(self._secret, nonce.encode("ascii"), hashlib.sha256).hexdigest()
        token = f"{nonce}.{signature}"
        now = time.time()
        expires_at = now + self.ttl_seconds
        with self._lock:
            self._prune_expired(now)
            if len(self._pending) >= self.max_pending:
                raise ConfirmationError("Limite de confirmações pendentes atingido; aguarde a expiração ou aplique as propostas existentes")
            self._pending[nonce] = Proposal(tool, self._digest(arguments), expires_at)
        return {"confirmationToken": token, "expiresInSeconds": self.ttl_seconds}

    def consume(self, token: str, tool: str, arguments: dict[str, Any]) -> None:
        try:
            nonce, signature = token.split(".", 1)
        except ValueError as exc:
            raise ConfirmationError("Token de confirmação inválido") from exc
        expected = hmac.new(self._secret, nonce.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ConfirmationError("Token de confirmação inválido")
        with self._lock:
            proposal = self._pending.pop(nonce, None)
        if proposal is None:
            raise ConfirmationError("Token de confirmação inexistente ou já utilizado")
        if time.time() > proposal.expires_at:
            raise ConfirmationError("Token de confirmação expirado")
        if proposal.tool != tool or proposal.arguments_digest != self._digest(arguments):
            raise ConfirmationError("Token não corresponde exatamente à operação preparada")
