"""Loads settings and registry (flat YAML) and builds the backend driver.

This is the only place that decides which driver to instantiate, so swapping
backend means adding a branch here and a new driver module — nothing else.
"""
import os
from pathlib import Path

from .core import Core
from .errors import ConfigError
from .drivers.onepassword_connect_server import OnePasswordConnectServerDriver

CONFIG_PATH = Path(os.environ.get("FF_SECRETS_CONFIG", "~/.config/ff-secrets/config.yaml")).expanduser()
DEFAULT_REGISTRY = "~/.config/ff-secrets/registry.yaml"


def _load_flat_yaml(path):
    """Parse a flat 'key: value' file. No nesting, no dependencies."""
    try:
        text = Path(path).read_text()
    except FileNotFoundError:
        raise ConfigError(f"file not found: {path}")
    data = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        data[key.strip()] = value.strip()
    return data


def _settings():
    return _load_flat_yaml(CONFIG_PATH) if CONFIG_PATH.exists() else {}


def build_driver():
    settings = _settings()
    kind = settings.get("driver", "1password-connect-server")
    if kind == "1password-connect-server":
        return OnePasswordConnectServerDriver(
            endpoint=settings.get("backend-endpoint"),
            bearer_path=settings.get("bearer-path"),
        )
    raise ConfigError(f"unknown driver: {kind}")


def registry_path():
    return Path(_settings().get("registry", DEFAULT_REGISTRY)).expanduser()


def load_registry():
    return _load_flat_yaml(registry_path())


def build_core():
    return Core(load_registry(), build_driver())
