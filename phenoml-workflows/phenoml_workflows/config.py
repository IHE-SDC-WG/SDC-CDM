from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

REQUIRED_KEYS = (
    "PHENOML_INSTANCE_URL",
    "PHENOML_CLIENT_ID",
    "PHENOML_CLIENT_SECRET",
)

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class PhenoConfig:
    instance_url: str
    client_id: str
    client_secret: str


def _parse_env_file() -> dict[str, str]:
    env_path = PACKAGE_ROOT / ".env"
    if not env_path.exists():
        return {}

    values: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def _merged_env(env: Optional[Mapping[str, str]] = None) -> dict[str, str]:
    return {**_parse_env_file(), **dict(env or os.environ)}


def get_config(env: Optional[Mapping[str, str]] = None) -> Optional[PhenoConfig]:
    config_env = _merged_env(env)
    instance_url = config_env.get("PHENOML_INSTANCE_URL")
    client_id = config_env.get("PHENOML_CLIENT_ID")
    client_secret = config_env.get("PHENOML_CLIENT_SECRET")

    if not instance_url or not client_id or not client_secret:
        return None

    return PhenoConfig(
        instance_url=instance_url,
        client_id=client_id,
        client_secret=client_secret,
    )


def require_config(env: Optional[Mapping[str, str]] = None) -> PhenoConfig:
    config = get_config(env)
    if config is not None:
        return config

    config_env = _merged_env(env)
    missing = [key for key in REQUIRED_KEYS if not config_env.get(key)]
    raise RuntimeError(
        f"PhenoML credentials not configured. Missing: {', '.join(missing)}"
    )


def create_client(config: PhenoConfig):
    from phenoml import PhenomlClient

    return PhenomlClient(
        base_url=config.instance_url,
        client_id=config.client_id,
        client_secret=config.client_secret,
    )
