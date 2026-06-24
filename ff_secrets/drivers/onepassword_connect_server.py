"""1Password Connect Server driver.

The only module that knows about 1Password: op:// references, the `op` CLI,
the 1Password Connect Server endpoint, and the bearer token in the macOS Keychain.
"""
import os
import subprocess

from .base import Driver
from ..errors import DriverError

KEYCHAIN_SERVICE = "ff-secrets"
KEYCHAIN_ACCOUNT = "1password-connect-server-bearer"


def _keychain_get(service, account):
    """Return the stored password, or None if absent."""
    result = subprocess.run(
        ["security", "find-generic-password", "-s", service, "-a", account, "-w"],
        capture_output=True, text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _keychain_set(service, account, value):
    """Create or update a generic password."""
    result = subprocess.run(
        ["security", "add-generic-password", "-U", "-s", service, "-a", account, "-w", value],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise DriverError(f"keychain write failed: {result.stderr.strip()}")


class OnePasswordConnectServerDriver(Driver):
    def __init__(self, endpoint=None):
        self._endpoint = endpoint

    def read(self, reference):
        try:
            result = subprocess.run(
                ["op", "read", reference],
                capture_output=True, text=True, env=self._op_env(),
            )
        except FileNotFoundError:
            raise DriverError("'op' not found in PATH (1Password CLI required)")
        if result.returncode != 0:
            raise DriverError(f"op read failed for {reference}: {result.stderr.strip()}")
        return result.stdout.rstrip("\n")

    def _op_env(self):
        if not self._endpoint:
            raise DriverError("missing 'endpoint' in config")
        token = _keychain_get(KEYCHAIN_SERVICE, KEYCHAIN_ACCOUNT)
        if token is None:
            raise DriverError("1Password Connect Server bearer token missing from Keychain — run: ff-secrets token set")
        env = dict(os.environ)
        env["OP_CONNECT_HOST"] = self._endpoint
        env["OP_CONNECT_TOKEN"] = token
        return env

    def set_credential(self, value):
        """Store or rotate the 1Password Connect Server bearer token in the Keychain."""
        _keychain_set(KEYCHAIN_SERVICE, KEYCHAIN_ACCOUNT, value)
