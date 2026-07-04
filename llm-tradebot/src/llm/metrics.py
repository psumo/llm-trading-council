from dataclasses import dataclass, asdict
from threading import Lock
from typing import Dict, Any


@dataclass
class LLMStats:
    total_requests: int = 0
    total_success: int = 0
    total_errors: int = 0
    last_latency_ms: int = 0
    total_latency_ms: int = 0
    min_latency_ms: int = 0
    max_latency_ms: int = 0
    last_error: str = ""
    last_request_ts: float = 0.0
    last_success_ts: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0

    def to_dict(self) -> Dict[str, Any]:
        avg_latency_ms = 0
        if self.total_success > 0:
            avg_latency_ms = int(self.total_latency_ms / self.total_success)
        token_speed_tps = 0.0
        if self.total_latency_ms > 0 and self.total_tokens > 0:
            token_speed_tps = self.total_tokens / (self.total_latency_ms / 1000.0)
        data = asdict(self)
        data.update({
            "avg_latency_ms": avg_latency_ms,
            "token_speed_tps": round(token_speed_tps, 2)
        })
        return data


_lock = Lock()
_stats_by_provider: Dict[str, LLMStats] = {}
_stats_by_model: Dict[str, LLMStats] = {}


def _get_or_create(map_ref: Dict[str, LLMStats], key: str) -> LLMStats:
    stat = map_ref.get(key)
    if stat is None:
        stat = LLMStats()
        map_ref[key] = stat
    return stat


def record_request(provider: str, model: str):
    with _lock:
        for key, store in ((provider, _stats_by_provider), (model, _stats_by_model)):
            stat = _get_or_create(store, key)
            stat.total_requests += 1
            stat.last_request_ts = __import__("time").time()


def record_success(provider: str, model: str, latency_ms: int, usage: Dict[str, Any] = None):
    with _lock:
        for key, store in ((provider, _stats_by_provider), (model, _stats_by_model)):
            stat = _get_or_create(store, key)
            stat.total_success += 1
            stat.last_latency_ms = int(latency_ms)
            stat.last_success_ts = __import__("time").time()
            stat.last_error = ""
            stat.total_latency_ms += int(latency_ms)
            if stat.min_latency_ms == 0 or latency_ms < stat.min_latency_ms:
                stat.min_latency_ms = int(latency_ms)
            if latency_ms > stat.max_latency_ms:
                stat.max_latency_ms = int(latency_ms)

            usage = usage or {}
            prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
            completion_tokens = int(usage.get("completion_tokens", 0) or 0)
            total_tokens = int(usage.get("total_tokens", 0) or 0)
            if total_tokens <= 0:
                total_tokens = prompt_tokens + completion_tokens
            stat.total_input_tokens += prompt_tokens
            stat.total_output_tokens += completion_tokens
            stat.total_tokens += total_tokens


def record_error(provider: str, model: str, error: str):
    with _lock:
        for key, store in ((provider, _stats_by_provider), (model, _stats_by_model)):
            stat = _get_or_create(store, key)
            stat.total_errors += 1
            stat.last_error = error


def snapshot() -> Dict[str, Any]:
    with _lock:
        return {
            "providers": {k: v.to_dict() for k, v in _stats_by_provider.items()},
            "models": {k: v.to_dict() for k, v in _stats_by_model.items()},
        }
