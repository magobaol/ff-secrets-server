"""Tests for the pure reconciliation logic in ff_secrets_server.sync."""
from ff_secrets_server import sync


def concealed(label, value=True):
    return {"label": label, "id": "", "type": "CONCEALED", "has_value": value}


def noise(label):
    return {"label": label, "id": "", "type": "STRING", "has_value": True}


def is_secret(field):
    return field["has_value"] and field["type"] == "CONCEALED"


def test_slugify():
    assert sync.slugify("credential") == "credential"
    assert sync.slugify("secret key") == "secret-key"
    assert sync.slugify("Valid From") == "valid-from"
    assert sync.slugify("API  Token") == "api-token"
    assert sync.slugify("a/b_c") == "a-b-c"
    assert sync.slugify("  trim  ") == "trim"


def test_parse_reference():
    assert sync.parse_reference("op://V/Item/field") == ("V", "Item", "field")
    assert sync.parse_reference("op://V/Item") is None
    assert sync.parse_reference("op://V/Item/f/extra") is None
    assert sync.parse_reference("not-a-ref") is None


def test_item_namespaces_basic():
    registry = {
        "airtable.credential": "op://API Secrets/Airtable API/credential",
        "switchbot.token": "op://API Secrets/Switchbot API/token",
        "switchbot.secret-key": "op://API Secrets/Switchbot API/secret key",
    }
    mapping = sync.item_namespaces(registry)
    assert mapping[("API Secrets", "Airtable API")] == "airtable"
    assert mapping[("API Secrets", "Switchbot API")] == "switchbot"


def test_vaults_in_registry_distinct_and_ordered():
    registry = {
        "a.x": "op://Vault A/I1/x",
        "b.y": "op://Vault B/I2/y",
        "c.z": "op://Vault A/I3/z",
    }
    assert sync.vaults_in_registry(registry) == ["Vault A", "Vault B"]


def test_discover_auto_add_for_known_item():
    registry = {"airtable.credential": "op://API Secrets/Airtable API/credential"}
    contents = {"API Secrets": [
        {"item": "Airtable API", "fields": [noise("notesPlain"), concealed("credential"), concealed("webhook")]},
    ]}
    result = sync.discover(registry, contents, is_secret)
    assert result["auto_adds"] == [("airtable.webhook", "op://API Secrets/Airtable API/webhook")]
    assert result["new_items"] == []
    assert result["prunes"] == []


def test_discover_new_item_groups_fields():
    registry = {"airtable.credential": "op://API Secrets/Airtable API/credential"}
    contents = {"API Secrets": [
        {"item": "Airtable API", "fields": [concealed("credential")]},
        {"item": "Switchbot API", "fields": [concealed("token"), concealed("secret key")]},
    ]}
    result = sync.discover(registry, contents, is_secret)
    assert result["auto_adds"] == []
    assert len(result["new_items"]) == 1
    new = result["new_items"][0]
    assert new["item"] == "Switchbot API"
    assert [name for name, _ in new["fields"]] == ["token", "secret key"]


def test_discover_skips_empty_and_noise_fields():
    registry = {}
    contents = {"V": [
        {"item": "I", "fields": [concealed("credential", value=False), noise("notesPlain")]},
    ]}
    result = sync.discover(registry, contents, is_secret)
    assert result["new_items"] == []
    assert result["auto_adds"] == []


def test_discover_prune_item_gone():
    registry = {"bear.iphone.credential": "op://API Secrets/Bear - iPhone/credential"}
    contents = {"API Secrets": [
        {"item": "Something Else", "fields": [concealed("credential")]},
    ]}
    result = sync.discover(registry, contents, is_secret)
    prune = result["prunes"][0]
    assert prune["alias"] == "bear.iphone.credential"
    assert prune["kind"] == "item"
    assert prune["item"] == "Bear - iPhone"


def test_discover_prune_field_gone():
    registry = {"airtable.token": "op://API Secrets/Airtable API/token"}
    contents = {"API Secrets": [
        {"item": "Airtable API", "fields": [concealed("credential")]},  # 'token' is gone
    ]}
    result = sync.discover(registry, contents, is_secret)
    prune = result["prunes"][0]
    assert prune["alias"] == "airtable.token"
    assert prune["kind"] == "field"
    assert prune["field"] == "token"


def test_discover_already_covered_is_noop():
    registry = {"airtable.credential": "op://API Secrets/Airtable API/credential"}
    contents = {"API Secrets": [
        {"item": "Airtable API", "fields": [concealed("credential")]},
    ]}
    result = sync.discover(registry, contents, is_secret)
    assert result["auto_adds"] == []
    assert result["new_items"] == []
    assert result["prunes"] == []


def test_discover_conflicting_namespace_warns_and_skips():
    # Same item mapped to two prefixes; a new field on it cannot be auto-named.
    registry = {
        "foo.credential": "op://V/Item/credential",
        "bar.token": "op://V/Item/token",
    }
    contents = {"V": [
        {"item": "Item", "fields": [concealed("credential"), concealed("token"), concealed("extra")]},
    ]}
    result = sync.discover(registry, contents, is_secret)
    assert result["auto_adds"] == []
    assert result["new_items"] == []
    assert any("multiple prefixes" in w for w in result["warnings"])


def test_discover_field_matched_by_id_is_covered():
    # A reference whose last segment is a field id (not label) must count as covered.
    registry = {"x.credential": "op://V/Item/abc123"}
    contents = {"V": [
        {"item": "Item", "fields": [{"label": "credential", "id": "abc123", "type": "CONCEALED", "has_value": True}]},
    ]}
    result = sync.discover(registry, contents, is_secret)
    # 'credential' label is a NEW eligible field (not the id-based ref), so it is proposed;
    # but the existing alias must NOT be pruned, since its id field is present.
    assert result["prunes"] == []
