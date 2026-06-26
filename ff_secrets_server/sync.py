"""Reconcile the registry with the backend vault: compute adds and prunes.

Pure logic, no I/O. Given the current registry and an enumeration of the
vault(s), it works out which aliases to add (eligible fields not yet
referenced) and which to prune (references whose item or field is gone).

The namespace for a brand-new item cannot be derived from the vault (1Password
holds no alias hint), so it is asked through the `ask_namespace` callback. For
items already in the registry the namespace is learned from the existing
aliases, so only genuinely new items need a human.
"""
import re

_CONFLICT = object()


def slugify(label):
    """Field label -> alias slug. The reference keeps the real label; the slug
    is only the cosmetic last segment of the alias (e.g. 'secret key' ->
    'secret-key')."""
    slug = label.strip().lower()
    slug = re.sub(r"[\s_/]+", "-", slug)
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    return re.sub(r"-+", "-", slug).strip("-")


def parse_reference(reference):
    """op://vault/item/field -> (vault, item, field), or None if not op://."""
    if not reference.startswith("op://"):
        return None
    parts = reference[len("op://"):].split("/")
    if len(parts) != 3:
        return None
    return tuple(parts)


def item_namespaces(registry):
    """Learn (vault, item) -> namespace from the existing registry.

    The namespace is the alias minus its last (field) segment. If one item is
    mapped to two different namespaces the entry is marked as a conflict, and
    sync will fall back to asking rather than guess.
    """
    mapping = {}
    for alias, reference in registry.items():
        parsed = parse_reference(reference)
        if not parsed:
            continue
        vault, item, _field = parsed
        namespace = alias.rsplit(".", 1)[0] if "." in alias else alias
        key = (vault, item)
        if key not in mapping:
            mapping[key] = namespace
        elif mapping[key] not in (namespace, _CONFLICT):
            mapping[key] = _CONFLICT
    return mapping


def vaults_in_registry(registry):
    """The distinct vault titles referenced by the registry, in first-seen order."""
    vaults = []
    for reference in registry.values():
        parsed = parse_reference(reference)
        if parsed and parsed[0] not in vaults:
            vaults.append(parsed[0])
    return vaults


def plan(registry, contents, ask_namespace, eligible):
    """Compute the sync plan.

    registry: dict alias -> reference (current state).
    contents: dict vault_title -> list of {item, fields:[{label,id,type,has_value}]}.
    ask_namespace(vault, item, field) -> namespace ('' to skip the item).
    eligible(field) -> bool: whether a field deserves an alias.

    Returns (adds, prunes, warnings):
      adds:   list of (alias, reference)
      prunes: list of (alias, reference, reason)
      warnings: list of str
    """
    adds, prunes, warnings = [], [], []
    namespaces = item_namespaces(registry)
    existing_refs = {ref.strip() for ref in registry.values()}
    taken_aliases = set(registry)

    # Index of fields present in the vault, for prune: (vault, item) -> {label|id}.
    present = {}
    for vault, items in contents.items():
        for entry in items:
            keys = set()
            for field in entry["fields"]:
                if field["label"]:
                    keys.add(field["label"])
                if field["id"]:
                    keys.add(field["id"])
            present[(vault, entry["item"])] = keys

    # ADD: eligible fields in the vault not yet referenced by any alias.
    for vault, items in contents.items():
        for entry in items:
            item = entry["item"]
            for field in entry["fields"]:
                if not eligible(field):
                    continue
                field_name = field["label"] or field["id"]
                reference = f"op://{vault}/{item}/{field_name}"
                if reference.strip() in existing_refs:
                    continue
                key = (vault, item)
                namespace = namespaces.get(key)
                if namespace is _CONFLICT:
                    warnings.append(f"item '{item}' maps to multiple namespaces in the registry; skipped {reference}")
                    continue
                if namespace is None:
                    namespace = ask_namespace(vault, item, field_name)
                    if not namespace:
                        continue
                    namespaces[key] = namespace  # reuse for further fields of the same new item
                alias = f"{namespace}.{slugify(field_name)}"
                if alias in taken_aliases:
                    warnings.append(f"alias '{alias}' already taken; skipped {reference}")
                    continue
                taken_aliases.add(alias)
                adds.append((alias, reference))

    # PRUNE: aliases whose referenced item or field no longer exists.
    for alias, reference in registry.items():
        parsed = parse_reference(reference)
        if not parsed:
            warnings.append(f"alias '{alias}' has a non-op:// reference, left as-is: {reference}")
            continue
        vault, item, field = parsed
        keys = present.get((vault, item))
        if keys is None:
            prunes.append((alias, reference, "item not found"))
        elif field not in keys:
            prunes.append((alias, reference, "field not found"))
    return adds, prunes, warnings
