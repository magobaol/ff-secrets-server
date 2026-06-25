"""1Password Connect Server driver, via the official onepasswordconnectsdk.

The only module that knows about 1Password: op:// references, the Connect SDK
and the bearer token. The bearer source is pluggable — keychain on macOS (dev),
file on the server (prod) — so the same driver runs in both places.
"""
import os
import subprocess

from .base import Driver
from ..errors import DriverError


def _bearer_from_keychain(service, account):
    result = subprocess.run(
        ["security", "find-generic-password", "-s", service, "-a", account, "-w"],
        capture_output=True, text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _bearer_from_file(path):
    try:
        return open(os.path.expanduser(path)).read().strip()
    except OSError:
        return None


class OnePasswordConnectServerDriver(Driver):
    def __init__(self, endpoint=None, bearer_source=None):
        self._endpoint = endpoint
        self._bearer_source = bearer_source or {"type": "keychain"}
        self._client = None  # lazy: built on first read

    def _bearer(self):
        kind = self._bearer_source.get("type")
        if kind == "keychain":
            token = _bearer_from_keychain(
                self._bearer_source.get("service", "ff-secrets"),
                self._bearer_source.get("account", "1password-connect-server-bearer"),
            )
        elif kind == "file":
            token = _bearer_from_file(self._bearer_source["path"])
        else:
            raise DriverError(f"unknown bearer source: {kind!r}")
        if not token:
            raise DriverError(f"bearer token not available from {kind} source")
        return token

    def _get_client(self):
        if self._client is None:
            if not self._endpoint:
                raise DriverError("missing 'endpoint' in config")
            try:
                from onepasswordconnectsdk.client import new_client
            except ImportError:
                raise DriverError("onepasswordconnectsdk not installed")
            self._client = new_client(self._endpoint, self._bearer())
        return self._client

    def read(self, reference):
        """Resolve an op://vault/item/field reference to its value."""
        if not reference.startswith("op://"):
            raise DriverError(f"not an op:// reference: {reference}")
        parts = reference[len("op://"):].split("/")
        if len(parts) != 3:
            raise DriverError(f"malformed op:// reference: {reference}")
        vault, item, field = parts
        try:
            it = self._get_client().get_item(item, vault)
        except Exception as e:
            raise DriverError(f"Connect get_item failed for {reference}: {e}")
        for f in it.fields:
            if field in ((f.label or ""), (f.id or "")):
                return f.value
        raise DriverError(f"field '{field}' not found in {reference}")
