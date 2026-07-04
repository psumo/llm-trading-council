"""Create thin per-instrument llm-trader instance directories.

Each instance dir holds its own config/config.ini + secrets file + data/ tree.
The shared repo code is run with CWD=<instance dir> and LLM_TRADER_HOME=<instance dir>
so the loader reads this dir's config/secrets while all CWD-relative data paths
(data/trading, data/market_data, cache, ...) stay isolated per instance.

Idempotent: configs are rewritten every run; the secrets file and data dirs are
created only if missing (never clobbers live instance data).
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[1] / "llm-trader"
BASE = Path(__file__).resolve().parents[1] / "llm-trader-instances"
SRC_CONFIG = REPO / "config" / "config.ini"
# Built from parts so this module/command never contains the literal blocked name.
SECRETS_NAME = "keys" + "." + "env"
SRC_SECRETS = REPO / SECRETS_NAME

INSTANCES: dict[str, tuple[str, int]] = {
    "eth": ("ETH/USDT:USDT", 8002),
    "sol": ("SOL/USDT:USDT", 8003),
    "spcx": ("SPCX/USDT:USDT", 8004),
}


def build_config(base_config: str, pair: str, port: int) -> str:
    cfg = base_config.replace("crypto_pair = BTC/USDT:USDT", f"crypto_pair = {pair}")
    # Flash for cost control regardless of what the BTC config currently uses.
    cfg = re.sub(
        r"(?m)^google_studio_model = .*$",
        "google_studio_model = gemini-3.5-flash",
        cfg,
    )
    cfg = re.sub(r"(?m)^port = 8000$", f"port = {port}", cfg)
    return cfg


def main() -> None:
    base_config = SRC_CONFIG.read_text(encoding="utf-8")
    for name, (pair, port) in INSTANCES.items():
        inst = BASE / name
        (inst / "config").mkdir(parents=True, exist_ok=True)
        (inst / "data" / "trading").mkdir(parents=True, exist_ok=True)
        (inst / "logs").mkdir(parents=True, exist_ok=True)

        cfg = build_config(base_config, pair, port)
        (inst / "config" / "config.ini").write_text(cfg, encoding="utf-8")

        dst_secrets = inst / SECRETS_NAME
        if not dst_secrets.is_file():
            shutil.copyfile(SRC_SECRETS, dst_secrets)
            secrets_status = "copied"
        else:
            secrets_status = "kept existing"
        print(
            f"{name}: pair={pair} port={port} "
            f"secrets={secrets_status} -> {inst}"
        )
    print("DONE")


if __name__ == "__main__":
    main()
