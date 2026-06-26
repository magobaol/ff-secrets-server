"""Integration tests for `registry sync` via the CLI, with fakes (no network)."""
import argparse
import io

from ff_secrets_server import cli, config


def concealed(label, value=True):
    return {"label": label, "id": "", "type": "CONCEALED", "has_value": value}


class FakeDriver:
    def __init__(self, items):
        self._items = items

    def list_items(self, vault):
        return self._items


class FakeStdin(io.StringIO):
    def isatty(self):
        return True


def wire(monkeypatch, tmp_path, registry, items, stdin=""):
    path = tmp_path / "registry.yaml"
    path.write_text("\n".join(f"{k}: {v}" for k, v in registry.items()) + "\n")
    monkeypatch.setattr(config, "load_registry", lambda: dict(registry))
    monkeypatch.setattr(config, "build_driver", lambda: FakeDriver(items))
    monkeypatch.setattr(config, "registry_path", lambda: path)
    monkeypatch.setattr("sys.stdin", FakeStdin(stdin))
    return path


def args(dry_run=False, yes=False):
    return argparse.Namespace(vault=None, dry_run=dry_run, yes=yes)


def test_sync_already_in_sync_writes_nothing(monkeypatch, tmp_path, capsys):
    registry = {"a.credential": "op://V/A/credential"}
    items = [{"item": "A", "fields": [concealed("credential")]}]
    path = wire(monkeypatch, tmp_path, registry, items)
    before = path.read_text()

    cli.cmd_registry_sync(args())

    assert "already in sync" in capsys.readouterr().err.lower()
    assert path.read_text() == before


def test_sync_dry_run_shows_plan_but_does_not_write(monkeypatch, tmp_path, capsys):
    registry = {
        "a.credential": "op://V/A/credential",
        "gone.credential": "op://V/Gone/credential",
    }
    items = [
        {"item": "A", "fields": [concealed("credential")]},
        {"item": "New Thing", "fields": [concealed("token")]},
    ]
    path = wire(monkeypatch, tmp_path, registry, items)
    before = path.read_text()

    cli.cmd_registry_sync(args(dry_run=True))

    err = capsys.readouterr().err
    assert "PLANNED CHANGES" in err
    assert "REMOVE" in err and "gone.credential" in err
    assert "dry run" in err.lower()
    assert path.read_text() == before  # untouched


def test_sync_interactive_adds_new_item_and_prunes(monkeypatch, tmp_path, capsys):
    registry = {
        "a.credential": "op://V/A/credential",
        "gone.credential": "op://V/Gone/credential",
    }
    items = [
        {"item": "A", "fields": [concealed("credential")]},
        {"item": "Switchbot API", "fields": [concealed("token"), concealed("secret key")]},
    ]
    path = wire(monkeypatch, tmp_path, registry, items, stdin="switchbot\ny\n")

    cli.cmd_registry_sync(args())

    result = path.read_text()
    assert "switchbot.token: op://V/Switchbot API/token" in result
    assert "switchbot.secret-key: op://V/Switchbot API/secret key" in result
    assert "a.credential: op://V/A/credential" in result
    assert "gone.credential" not in result  # pruned


def test_sync_aborted_on_no_confirmation(monkeypatch, tmp_path, capsys):
    registry = {"gone.credential": "op://V/Gone/credential"}
    items = [{"item": "Other", "fields": [concealed("credential")]}]
    path = wire(monkeypatch, tmp_path, registry, items, stdin="n\n")
    before = path.read_text()

    cli.cmd_registry_sync(args())

    assert "aborted" in capsys.readouterr().err.lower()
    assert path.read_text() == before
