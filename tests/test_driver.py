"""Tests for the 1Password Connect driver, with a fake SDK client (no network)."""
from types import SimpleNamespace

import pytest

from ff_secrets_server.drivers.onepassword_connect_server import OnePasswordConnectServerDriver
from ff_secrets_server.errors import DriverError


def field(label="", id="", type="CONCEALED", value=None):
    return SimpleNamespace(label=label, id=id, type=type, value=value)


class FakeClient:
    def __init__(self, items_by_title=None, vault_id="vid", summaries=None):
        self._items = items_by_title or {}
        self._vault_id = vault_id
        self._summaries = summaries or []

    def get_item(self, item, vault):
        return self._items[item]

    def get_vault_by_title(self, title):
        return SimpleNamespace(id=self._vault_id, title=title)

    def get_items(self, vault_id):
        return self._summaries


def driver_with(client):
    driver = OnePasswordConnectServerDriver(endpoint="http://x", bearer_path="/dev/null")
    driver._client = client  # bypass lazy SDK construction
    return driver


def test_read_rejects_non_op_reference():
    driver = driver_with(FakeClient())
    with pytest.raises(DriverError):
        driver.read("https://example.com")


def test_read_rejects_malformed_reference():
    driver = driver_with(FakeClient())
    with pytest.raises(DriverError):
        driver.read("op://Vault/Item")  # missing field segment


def test_read_matches_field_by_label():
    item = SimpleNamespace(fields=[field(label="credential", value="s3cr3t")])
    driver = driver_with(FakeClient(items_by_title={"Item": item}))
    assert driver.read("op://Vault/Item/credential") == "s3cr3t"


def test_read_matches_field_by_id():
    item = SimpleNamespace(fields=[field(label="credential", id="abc", value="byid")])
    driver = driver_with(FakeClient(items_by_title={"Item": item}))
    assert driver.read("op://Vault/Item/abc") == "byid"


def test_read_field_not_found_raises():
    item = SimpleNamespace(fields=[field(label="credential", value="x")])
    driver = driver_with(FakeClient(items_by_title={"Item": item}))
    with pytest.raises(DriverError):
        driver.read("op://Vault/Item/missing")


def test_list_items_returns_metadata_only_and_skips_trashed():
    live = SimpleNamespace(id="1", title="Live", trashed=False)
    gone = SimpleNamespace(id="2", title="Trashed", trashed=True)
    full = SimpleNamespace(title="Live", fields=[
        field(label="credential", type="CONCEALED", value="secret"),
        field(label="notesPlain", type="STRING", value=None),
    ])
    # list_items fetches the full item by summary id, so key the fake by id.
    client = FakeClient(items_by_title={"1": full}, summaries=[live, gone])
    driver = driver_with(client)

    items = driver.list_items("API Secrets")
    assert len(items) == 1
    entry = items[0]
    assert entry["item"] == "Live"
    fields = {f["label"]: f for f in entry["fields"]}
    assert fields["credential"]["type"] == "CONCEALED"
    assert fields["credential"]["has_value"] is True
    assert fields["notesPlain"]["has_value"] is False
    # the secret value is never carried in the metadata
    assert "value" not in fields["credential"]
