"""1Password Connect Server driver, via the official onepasswordconnectsdk.

The only module that knows about 1Password: op:// references, the Connect SDK
and the bearer token. The bearer is read from a file (bearer-path): the server
runs on Lisa, where the token lives in a file mounted into the container.
"""
import os

from .base import Driver
from ..errors import DriverError


def _bearer_from_file(path):
    try:
        return open(os.path.expanduser(path)).read().strip()
    except OSError:
        return None


class OnePasswordConnectServerDriver(Driver):
    def __init__(self, endpoint=None, bearer_path=None):
        self._endpoint = endpoint
        self._bearer_path = bearer_path
        self._client = None  # lazy: built on first read

    def _bearer(self):
        if not self._bearer_path:
            raise DriverError("missing 'bearer-path' in config")
        token = _bearer_from_file(self._bearer_path)
        if not token:
            raise DriverError(f"bearer token not available from file: {self._bearer_path}")
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

    def list_items(self, vault):
        """Enumerate a vault: every item with its field metadata (no values)."""
        client = self._get_client()
        try:
            v = client.get_vault_by_title(vault)
        except Exception as e:
            raise DriverError(f"Connect get_vault failed for '{vault}': {e}")
        try:
            summaries = client.get_items(v.id)
        except Exception as e:
            raise DriverError(f"Connect get_items failed for '{vault}': {e}")
        items = []
        for s in summaries:
            if getattr(s, "trashed", False):
                continue
            full = client.get_item(s.id, v.id)
            fields = [
                {
                    "label": f.label or "",
                    "id": f.id or "",
                    "type": f.type or "",
                    "has_value": bool(getattr(f, "value", None)),
                }
                for f in (full.fields or [])
            ]
            items.append({"item": full.title, "fields": fields})
        return items
