"""Configuration loading: built-in defaults deep-merged with a user TOML file."""
from __future__ import annotations

import copy
import os
import sys
from pathlib import Path
from typing import Any, Optional

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised on 3.9/3.10 only
    import tomli as tomllib

ENV_CONFIG = "WEEKLY_REPORT_CONFIG"

DEFAULTS: dict[str, Any] = {
    "provider": "openai",
    "language": "zh",            # zh | en
    "author_name": "",
    "output_dir": "~/weekly-reports",
    "default_week": "last",      # this | last | prev
    "template": "",              # custom template path; empty = built-in
    "extra_instructions": "",    # appended to the system prompt
    "max_context_chars": 60000,
    "git": {
        "enabled": True,
        "roots": ["~/code"],
        "authors": [],           # empty = each repo's own `git config user.email`
        "max_depth": 4,
        "exclude": [],           # substrings matched against repo paths
    },
    "agents": {
        "enabled": True,
        "sources": ["claude", "codex", "kiro", "kiro-cli"],
        "include_prompts": True,  # False = only send session titles, not your prompts
        "max_prompt_len": 160,
        "max_prompts_per_session": 8,
        "exclude": [],           # substrings matched against session working dirs
        "roots": {},             # override record directories, e.g. {claude = "..."}
    },
    "providers": {},
    "email": {
        "method": "smtp",        # smtp | agently
        "to": [],
        "cc": [],
        "subject": "",           # empty = built-in, supports {title} {name} {start} {end} {label}
        "smtp": {
            "host": "",
            "port": 465,
            "security": "ssl",   # ssl | starttls | none
            "username": "",
            "password_env": "SMTP_PASSWORD",
            "from": "",
        },
    },
}


def default_config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "weekly-report" / "config.toml"


def resolve_config_path(explicit: Optional[str] = None) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    env = os.environ.get(ENV_CONFIG)
    if env:
        return Path(env).expanduser()
    return default_config_path()


def deep_merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


class ConfigError(Exception):
    pass


def read_user_toml(path: Path) -> dict:
    """The raw user TOML (no defaults merged); raises TOMLDecodeError on bad syntax."""
    with path.open("rb") as fh:
        return tomllib.load(fh)


def load_config(path: Optional[str] = None) -> tuple[dict, Optional[Path]]:
    """Return (config, loaded_path). loaded_path is None when no file exists."""
    cfg_path = resolve_config_path(path)
    if not cfg_path.is_file():
        if path:  # an explicitly requested file must exist
            raise ConfigError(f"config file not found: {cfg_path}")
        return copy.deepcopy(DEFAULTS), None
    try:
        user = read_user_toml(cfg_path)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {cfg_path}: {exc}") from exc
    return deep_merge(DEFAULTS, user), cfg_path


def expand(path: str) -> Path:
    return Path(os.path.expandvars(path)).expanduser()
