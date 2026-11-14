import math
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Final

from gateway_service.domain import RateDecision, RateLimit
from gateway_service.ports import Clock

DEFAULT_MAX_KEYS: Final = 100_000
# Soma de frações do relógio (11.9 + 0.1) não pode negar a ficha que já encheu
_EPSILON: Final = 1e-9


@dataclass(slots=True)
class _Bucket:
    tokens: float
    updated_at: float
    full_at: float


class InMemoryTokenBucket:
    """Buckets por processo; sem await no hit, então é atômico no event loop"""

    def __init__(self, *, clock: Clock = time.monotonic, max_keys: int = DEFAULT_MAX_KEYS) -> None:
        self._clock = clock
        # Teto por política: uma rajada de logins não despeja os buckets do cadastro
        self._max_keys = max_keys
        # Ordenados pela última atualização: o início é o candidato a limpeza e a despejo
        self._policies: dict[str, OrderedDict[str, _Bucket]] = {}

    def __len__(self) -> int:
        return sum(len(buckets) for buckets in self._policies.values())

    async def hit(self, key: str, limit: RateLimit) -> RateDecision:
        now = self._clock()
        for policy_buckets in self._policies.values():
            _drop_refilled(policy_buckets, now)
        buckets = self._policies.setdefault(limit.name, OrderedDict())
        rate = limit.capacity / limit.period_seconds
        bucket = buckets.get(key)
        tokens = float(limit.capacity)
        if bucket is not None:
            tokens = min(tokens, bucket.tokens + (now - bucket.updated_at) * rate)

        if tokens >= 1 - _EPSILON:
            tokens = max(0.0, tokens - 1)
            decision = RateDecision(allowed=True)
        else:
            # Negar não consome: o Retry-After de quem martela não cresce sem fim
            wait = (1 - tokens) / rate
            decision = RateDecision(allowed=False, retry_after=max(1, math.ceil(wait - _EPSILON)))

        full_at = now + (limit.capacity - tokens) / rate
        buckets[key] = _Bucket(tokens, now, full_at)
        buckets.move_to_end(key)
        while len(buckets) > self._max_keys:
            buckets.popitem(last=False)
        return decision


def _drop_refilled(buckets: OrderedDict[str, _Bucket], now: float) -> None:
    """Bucket cheio equivale a não existir; amortizado O(1)"""
    while buckets:
        oldest = next(iter(buckets.values()))
        if oldest.full_at > now:
            return
        buckets.popitem(last=False)
