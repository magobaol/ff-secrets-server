"""Tests for registry file editing: add, apply_changes, atomic write."""
import os
import stat

from ff_secrets_server import registry


HEADER = "# ff-secrets registry\n# convention note\n\n"


def write_registry(tmp_path, body):
    path = tmp_path / "registry.yaml"
    path.write_text(HEADER + body)
    return path


def read_lines(path):
    return path.read_text().splitlines()


def test_add_new_alias_appends(tmp_path):
    path = write_registry(tmp_path, "a.x: op://V/A/x\n")
    updated = registry.add(str(path), "b.y", "op://V/B/y")
    assert updated is False
    lines = read_lines(path)
    assert "b.y: op://V/B/y" in lines
    assert lines[0] == "# ff-secrets registry"  # comments preserved


def test_add_existing_alias_updates_in_place(tmp_path):
    path = write_registry(tmp_path, "a.x: op://V/A/old\n")
    updated = registry.add(str(path), "a.x", "op://V/A/new")
    assert updated is True
    assert "a.x: op://V/A/new" in read_lines(path)
    assert "a.x: op://V/A/old" not in read_lines(path)


def test_apply_changes_adds_and_prunes_preserving_order(tmp_path):
    path = write_registry(tmp_path, "a.x: op://V/A/x\nb.y: op://V/B/y\nc.z: op://V/C/z\n")
    adds = [("d.w", "op://V/D/w")]
    prunes = [("b.y", "op://V/B/y", "item")]
    registry.apply_changes(str(path), adds, prunes)
    lines = [l for l in read_lines(path) if l and not l.startswith("#")]
    assert lines == ["a.x: op://V/A/x", "c.z: op://V/C/z", "d.w: op://V/D/w"]
    # comments survive
    assert read_lines(path)[0].startswith("#")


def test_apply_changes_preserves_mode(tmp_path):
    path = write_registry(tmp_path, "a.x: op://V/A/x\n")
    os.chmod(path, 0o644)
    registry.apply_changes(str(path), [("b.y", "op://V/B/y")], [])
    mode = stat.S_IMODE(os.stat(path).st_mode)
    assert mode == 0o644


def test_apply_changes_no_op_keeps_file(tmp_path):
    path = write_registry(tmp_path, "a.x: op://V/A/x\n")
    before = path.read_text()
    registry.apply_changes(str(path), [], [])
    assert path.exists()
    assert path.read_text() == before


def test_atomic_write_leaves_no_temp_files(tmp_path):
    path = write_registry(tmp_path, "a.x: op://V/A/x\n")
    registry.apply_changes(str(path), [("b.y", "op://V/B/y")], [])
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.startswith(".registry-")]
    assert leftovers == []
