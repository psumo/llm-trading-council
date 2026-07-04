"""Configuration loading and validation for the confluence aggregator.

Reads config.yaml, validates it with pydantic, and fails fast with clear
errors. The orderflow DB password is never stored in config -- it is read
at runtime from the orderflow .env file referenced here.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

# Repo-relative default paths (portable across machines/clones).
from pathlib import Path as _Path
_AGGREGATOR_DIR = _Path(__file__).resolve().parent
_STACK_ROOT = _AGGREGATOR_DIR.parent


class DashboardCfg(BaseModel):
    host: str = "127.0.0.1"
    port: int = Field(8500, ge=1, le=65535)


class LlmTraderCfg(BaseModel):
    enabled: bool = True
    db_path: str
    last_analysis_path: str
    staleness_seconds: int = Field(1800, ge=1)


class LlmTraderPathsCfg(BaseModel):
    """Per-instrument override of the llm_trader data-file locations.

    Each single-pair llm-trader instance writes its own ``trade_history.db`` and
    ``last_analysis.json`` under its own data dir. When an instrument sets these
    paths they take precedence over the global ``llm_trader`` block, letting one
    aggregator read a distinct trader instance per symbol. ``previous_response.json``
    is derived from ``last_analysis_path``'s parent dir (see LlmTraderSource), so
    pointing these at the right instance dir is sufficient.
    """

    db_path: str
    last_analysis_path: str


class LlmTradebotCfg(BaseModel):
    enabled: bool = True
    base_url: str
    password: str
    staleness_seconds: int = Field(1800, ge=1)
    request_timeout_seconds: float = Field(8.0, gt=0)

    @field_validator("base_url")
    @classmethod
    def _strip_slash(cls, v: str) -> str:
        return v.rstrip("/")


class OrderflowCfg(BaseModel):
    enabled: bool = True
    host: str = "127.0.0.1"
    port: int = Field(5455, ge=1, le=65535)
    user: str = "postgres"
    db: str = "postgres"
    env_path: str
    staleness_seconds: int = Field(300, ge=1)
    request_timeout_seconds: float = Field(8.0, gt=0)
    interval: str = "1m"
    lookback_candles: int = Field(5, ge=1, le=100)
    tick_size: float = Field(0.01, gt=0)
    imbalance_ratio: float = Field(3.0, gt=1)
    stacked_levels: int = Field(3, ge=2)
    delta_min_abs: float = Field(0.0, ge=0)


class JudgeCfg(BaseModel):
    enabled: bool = True
    # gemini-3.5-flash = fast/cheap default. gemini-3.1-pro-preview is the
    # stronger (slower/pricier) option -- swap here if you want more rigor.
    model: str = "gemini-3.5-flash"
    # Read at runtime from the llm-tradebot .env (GEMINI_API_KEY=...). Never
    # stored in this config. Override the path only if the bot moves.
    api_key_env_path: str = (
        str(_STACK_ROOT / "llm-tradebot" / ".env")
    )
    min_interval_seconds: int = Field(120, ge=1)
    max_age_seconds: int = Field(300, ge=1)
    alert_conviction: int = Field(60, ge=0, le=100)
    timeout_seconds: float = Field(30.0, gt=0)
    # How many recent closed positions to surface in the judge MEMORY section.
    memory_last_n: int = Field(10, ge=0, le=100)
    # entry_conviction at/above which the judge would ACT (enter). Below this is
    # a no-trade (FLAT). Fed into the prompt's calibration block.
    act_threshold: float = Field(50.0, ge=0, le=100)
    # R:R floor for scalps fed into the prompt (prefer higher, don't demand 2.0).
    rr_floor: float = Field(1.3, gt=0)


class ScorecardsCfg(BaseModel):
    enabled: bool = True
    # A recorded voice signal resolves once this many minutes have elapsed.
    horizon_minutes: float = Field(60.0, gt=0)
    # Minimum |price move %| to count a signal as right/wrong (else "flat").
    min_move_pct: float = Field(0.1, ge=0)
    # Rolling window of resolved signals used for the per-voice stats.
    window: int = Field(50, ge=1, le=10000)


class ReflectionCfg(BaseModel):
    enabled: bool = True
    # Minimum new closed trades since the last reflection to trigger one.
    min_new_trades: int = Field(5, ge=1)
    # Never reflect more often than this many hours apart.
    min_interval_hours: float = Field(24.0, gt=0)
    # Retire lessons older than this many days that are not re-confirmed.
    max_lesson_age_days: float = Field(30.0, gt=0)
    # Lessons file (JSON). Defaults to data/lessons.json beside the db.
    lessons_path: str = (
        str(_AGGREGATOR_DIR / "data" / "lessons.json")
    )


class TrackerCfg(BaseModel):
    enabled: bool = True
    # Minimum judge ENTRY_CONVICTION to open a paper position (the decoupled
    # conviction-to-enter signal, not flat_confidence).
    min_conviction: float = Field(50.0, ge=0, le=100)
    # Percent of current balance risked per trade (entry-to-stop distance).
    risk_pct: float = Field(1.0, gt=0, le=100)
    start_balance: float = Field(1000.0, gt=0)
    max_hold_hours: float = Field(12.0, gt=0)
    # Minimum ACTUAL risk:reward (recomputed from entry/SL/TP at open, NOT the
    # judge's claimed value) required to open. Rejects degenerate-TP trades
    # whose reward is near-zero after fees. Mirrors judge.rr_floor.
    rr_floor: float = Field(1.3, gt=0)
    # When false, skip the Binance REST price poll and use the orderflow
    # footprint close as the only price source.
    price_poll: bool = True
    price_timeout_seconds: float = Field(5.0, gt=0)
    db_path: str = (
        str(_AGGREGATOR_DIR / "data" / "positions.db")
    )


class GuardsCfg(BaseModel):
    """Pre-execution guard pipeline thresholds.

    Each field tunes one guard in guards.py. Defaults encode the lessons from 7
    logged losing trades (single-voice opens, sub-0.1% stops, an unthrottled
    loss streak). See config.yaml for the annotated values.
    """

    enabled: bool = True
    # Agreement floor counted only over the PERMISSION voices (llm_trader,
    # llm_tradebot). The judge already fuses the signals; this is a sanity floor,
    # not an AND-gate. Order flow is a trigger, not a vetoing vote.
    min_agree: int = Field(1, ge=1)
    min_stop_pct: float = Field(0.10, gt=0)
    cooldown_losses: int = Field(3, ge=1)
    cooldown_minutes: int = Field(120, ge=0)
    max_daily_loss_r: float = Field(3.0, gt=0)
    max_concurrent: int = Field(3, ge=1)


class ConfluenceCfg(BaseModel):
    weights: dict[str, float] = Field(default_factory=dict)
    alert_min_agree: int = Field(2, ge=1)
    strong_min_agree: int = Field(3, ge=1)


# Voices a per-instrument engine may run. llm_trader is single-pair (BTC only);
# tradebot + orderflow are parameterised by symbol.
_VALID_VOICES = ("llm_trader", "llm_tradebot", "orderflow")


class InstrumentCfg(BaseModel):
    """One traded symbol with its timeframes, active voices and (optional)
    per-instrument confluence override.

    `voices` selects which sources run for this symbol. ETH/SOL omit
    `llm_trader` (it only analyses BTC). `confluence` overrides the global
    thresholds so a 2-voice instrument can ALERT on 2/2 agreement.
    """

    symbol: str
    timeframes: list[str] = Field(default_factory=lambda: ["5m", "15m", "1h"])
    voices: list[str] = Field(default_factory=lambda: list(_VALID_VOICES))
    confluence: ConfluenceCfg | None = None
    # Optional per-instrument llm_trader file locations. When set, override the
    # global `llm_trader:` db_path/last_analysis_path so each symbol can read its
    # own single-pair trader instance.
    llm_trader_paths: LlmTraderPathsCfg | None = None

    @field_validator("symbol")
    @classmethod
    def _symbol_upper(cls, v: str) -> str:
        v = v.strip().upper()
        if not v:
            raise ValueError("instrument symbol must be non-empty")
        return v

    @field_validator("voices")
    @classmethod
    def _validate_voices(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("instrument must have at least one voice")
        bad = [s for s in v if s not in _VALID_VOICES]
        if bad:
            raise ValueError(
                f"unknown voice(s) {bad}; valid: {list(_VALID_VOICES)}"
            )
        # De-duplicate while preserving order.
        seen: dict[str, None] = {}
        for s in v:
            seen.setdefault(s, None)
        return list(seen.keys())

    @field_validator("timeframes")
    @classmethod
    def _validate_timeframes(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("instrument must have at least one timeframe")
        seen: dict[str, None] = {}
        for tf in v:
            seen.setdefault(str(tf).strip(), None)
        return list(seen.keys())

    def effective_confluence(self, default: ConfluenceCfg) -> ConfluenceCfg:
        """This instrument's confluence config, defaulting sensibly.

        With only 2 voices, an ALERT needs both to agree and a STRONG needs
        all of them -- so the thresholds are clamped to the voice count when
        no explicit override is given.
        """
        if self.confluence is not None:
            return self.confluence
        n = len(self.voices)
        return ConfluenceCfg(
            weights=dict(default.weights),
            alert_min_agree=min(default.alert_min_agree, n),
            strong_min_agree=min(default.strong_min_agree, n),
        )


class NotifyCfg(BaseModel):
    enabled: bool = True
    cooldown_seconds: int = Field(600, ge=0)
    toast_app_id: str = "Confluence Aggregator"


class PersistenceCfg(BaseModel):
    events_path: str
    max_log_events: int = Field(50, ge=1, le=10000)


class Config(BaseModel):
    # Multi-pair: `instruments` is the source of truth. Legacy single-symbol
    # configs (a top-level `symbol:` with no `instruments:`) are migrated into a
    # one-instrument list by the validator below so old configs keep working.
    instruments: list[InstrumentCfg] = Field(default_factory=list)
    # Legacy single-symbol key. When present and `instruments` is empty it is
    # migrated; it is also kept as the "primary" symbol for back-compat fields.
    symbol: str | None = None
    dashboard: DashboardCfg
    poll_interval_seconds: float = Field(15.0, gt=0)
    llm_trader: LlmTraderCfg
    llm_tradebot: LlmTradebotCfg
    orderflow: OrderflowCfg
    confluence: ConfluenceCfg
    notify: NotifyCfg
    persistence: PersistenceCfg
    judge: JudgeCfg
    tracker: TrackerCfg
    scorecards: ScorecardsCfg
    reflection: ReflectionCfg
    guards: GuardsCfg = Field(default_factory=lambda: GuardsCfg())  # type: ignore[call-arg]

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_symbol(cls, data: Any) -> Any:
        """Accept a legacy single-`symbol` config by synthesising one
        instrument from it. If neither `instruments` nor `symbol` is given the
        normal validation error fires with a migration hint."""
        if not isinstance(data, dict):
            return data
        instruments = data.get("instruments")
        symbol = data.get("symbol")
        if not instruments:
            if symbol:
                data["instruments"] = [{"symbol": symbol}]
            else:
                raise ValueError(
                    "config must define `instruments:` (a list of "
                    "{symbol, timeframes, voices}). Legacy single-symbol "
                    "configs may instead set a top-level `symbol:` which will "
                    "be migrated automatically -- please migrate to "
                    "`instruments:`."
                )
        return data

    @model_validator(mode="after")
    def _set_primary_symbol(self) -> "Config":
        """Ensure `symbol` always reflects the first instrument (back-compat
        for /api/health and startup banners)."""
        if self.instruments and not self.symbol:
            object.__setattr__(self, "symbol", self.instruments[0].symbol)
        return self

    @property
    def primary_symbol(self) -> str:
        if self.instruments:
            return self.instruments[0].symbol
        return self.symbol or "BTCUSDT"


def read_orderflow_password(env_path: str) -> str | None:
    """Extract POSTGRES_PASSWORD / DB password from an orderflow .env file.

    Returns None if the file is missing or no password key is present. Never
    raises -- a missing password just means the orderflow source goes offline.
    """
    path = Path(env_path)
    if not path.is_file():
        return None
    # Keys we accept, in priority order.
    keys = (
        "POSTGRES_PASSWORD",
        "DB_PASSWORD",
        "PGPASSWORD",
        "DATABASE_PASSWORD",
    )
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    found: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k in keys and v:
            found[k] = v
    for key in keys:
        if key in found:
            return found[key]
    # Fallback: a DSN-style line like DATABASE_URL=postgres://user:pass@host/db
    dsn_match = re.search(r"://[^:/@]+:([^@/]+)@", text)
    if dsn_match:
        return dsn_match.group(1)
    return None


def read_gemini_key(env_path: str) -> str | None:
    """Extract GEMINI_API_KEY from the llm-tradebot .env file.

    Same defensive pattern as read_orderflow_password: never raises, returns
    None when the file is missing or the key is absent so the judge can degrade
    to a clear "no API key" status instead of crashing.
    """
    path = Path(env_path)
    if not path.is_file():
        return None
    keys = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GEMINI_KEY")
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    found: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k in keys and v:
            found[k] = v
    for key in keys:
        if key in found:
            return found[key]
    return None


def load_config(path: str | Path) -> Config:
    """Load and validate config.yaml. Raises SystemExit with a clear message
    on any structural or validation error so startup fails fast."""
    cfg_path = Path(path)
    if not cfg_path.is_file():
        raise SystemExit(f"[config] file not found: {cfg_path}")
    try:
        raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise SystemExit(f"[config] invalid YAML in {cfg_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise SystemExit(f"[config] top level of {cfg_path} must be a mapping")
    try:
        return Config(**raw)
    except ValidationError as exc:
        lines = "\n".join(
            f"  - {'.'.join(str(p) for p in e['loc'])}: {e['msg']}"
            for e in exc.errors()
        )
        raise SystemExit(f"[config] validation failed for {cfg_path}:\n{lines}") from exc
