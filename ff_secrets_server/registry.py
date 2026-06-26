"""Registry file management: alias -> reference, flat YAML, edited in place.

Only the server owns the registry; these helpers back the `registry` admin commands.
"""
import os
import tempfile
from pathlib import Path


def _atomic_write(path, text):
    """Write via a temp file in the same directory + os.replace, so a reader
    (the hot-reloading server) never sees a half-written registry."""
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".registry-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def add(registry_path, alias, reference):
    """Add or update `alias: reference`. Returns True if it updated an existing alias."""
    path = Path(registry_path).expanduser()
    lines = path.read_text().splitlines() if path.exists() else []
    out, found = [], False
    for line in lines:
        s = line.strip()
        if s and not s.startswith("#") and ":" in line and line.split(":", 1)[0].strip() == alias:
            out.append(f"{alias}: {reference}")
            found = True
        else:
            out.append(line)
    if not found:
        out.append(f"{alias}: {reference}")
    _atomic_write(path, "\n".join(out) + "\n")
    return found


def apply_changes(registry_path, adds, prunes):
    """Apply a sync plan to the registry file, preserving comments and order.

    adds: iterable of (alias, reference) appended at the end.
    prunes: iterable of (alias, reference, reason); the alias lines are dropped.
    Existing aliases keep their position. Written atomically.
    """
    path = Path(registry_path).expanduser()
    prune_aliases = {alias for alias, _ref, _reason in prunes}
    lines = path.read_text().splitlines() if path.exists() else []
    out = []
    for line in lines:
        s = line.strip()
        if s and not s.startswith("#") and ":" in line and line.split(":", 1)[0].strip() in prune_aliases:
            continue
        out.append(line)
    for alias, reference in adds:
        out.append(f"{alias}: {reference}")
    _atomic_write(path, "\n".join(out) + "\n")
