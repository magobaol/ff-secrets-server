"""Tests for flat-YAML parsing (the only config format ff-secrets-server uses)."""
from ff_secrets_server import config


def test_load_flat_yaml_basic(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text("driver: 1password-connect-server\nregistry: /app/data/registry.yaml\n")
    data = config._load_flat_yaml(path)
    assert data["driver"] == "1password-connect-server"
    assert data["registry"] == "/app/data/registry.yaml"


def test_load_flat_yaml_splits_only_on_first_colon(tmp_path):
    # op:// references contain colons; the value must keep them intact.
    path = tmp_path / "r.yaml"
    path.write_text("airtable.credential: op://API Secrets/Airtable API/credential\n")
    data = config._load_flat_yaml(path)
    assert data["airtable.credential"] == "op://API Secrets/Airtable API/credential"


def test_load_flat_yaml_ignores_comments_and_blanks(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text("# a comment\n\nkey: value\n   \n# trailing\n")
    data = config._load_flat_yaml(path)
    assert data == {"key": "value"}
