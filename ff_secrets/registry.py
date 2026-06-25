"""Registry file management: alias -> reference, flat YAML, edited in place.

Only the server owns the registry; these helpers back the `registry` admin commands.
"""
from pathlib import Path


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
    path.write_text("\n".join(out) + "\n")
    return found
