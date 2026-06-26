"""Tests for the backend-agnostic core, including registry hot-reload."""
import pytest

from ff_secrets_server.core import Core
from ff_secrets_server.errors import UnknownAlias


class EchoDriver:
    """A driver that returns the reference itself, so tests can assert routing."""
    def read(self, reference):
        return f"resolved:{reference}"


def test_read_resolves_alias_through_driver():
    core = Core(lambda: {"a.x": "op://V/A/x"}, EchoDriver())
    assert core.read("a.x") == "resolved:op://V/A/x"


def test_read_unknown_alias_raises():
    core = Core(lambda: {}, EchoDriver())
    with pytest.raises(UnknownAlias):
        core.read("missing")


def test_aliases_filtered_and_sorted():
    registry = {"b.y": "op://V/B/y", "a.x": "op://V/A/x", "a.z": "op://V/A/z"}
    core = Core(lambda: registry, EchoDriver())
    assert core.aliases() == ["a.x", "a.z", "b.y"]
    assert core.aliases("a.") == ["a.x", "a.z"]


def test_registry_is_reread_per_request_hot_reload():
    store = {"a.x": "op://V/A/x"}
    core = Core(lambda: dict(store), EchoDriver())
    assert core.read("a.x") == "resolved:op://V/A/x"
    store["a.x"] = "op://V/A/changed"  # edit the registry between requests
    assert core.read("a.x") == "resolved:op://V/A/changed"
