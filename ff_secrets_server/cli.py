"""Command-line surface: parses arguments and drives the core."""
import argparse
import os
import re
import sys
from pathlib import Path

from . import config
from .errors import FfSecretsError

MARKER_RE = re.compile(r"ffsec:([A-Za-z0-9._-]+)")


def cmd_read(args):
    value = config.build_core().read(args.alias)
    sys.stdout.write(value + ("\n" if args.newline else ""))


def cmd_list(args):
    for alias in config.build_core().aliases(args.prefix):
        print(alias)


def cmd_run(args):
    command = args.command[1:] if args.command and args.command[0] == "--" else args.command
    if not command:
        raise FfSecretsError("missing command after '--'")
    core = config.build_core()
    specs = list(args.env or [])
    if args.env_file:
        for line in Path(args.env_file).expanduser().read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                specs.append(line)
    # The child's environment only gets the requested secrets, never the
    # 1Password Connect Server token (which lives inside the driver's own environment).
    env = dict(os.environ)
    for spec in specs:
        if "=" not in spec:
            raise FfSecretsError(f"malformed --env (expected VAR=alias): {spec}")
        var, alias = spec.split("=", 1)
        env[var.strip()] = core.read(alias.strip())
    os.execvpe(command[0], command, env)


def cmd_inject(args):
    core = config.build_core()
    text = Path(args.input).expanduser().read_text() if args.input else sys.stdin.read()
    resolved = MARKER_RE.sub(lambda m: core.read(m.group(1)), text)
    if args.output:
        Path(args.output).expanduser().write_text(resolved)
    else:
        sys.stdout.write(resolved)


def cmd_serve(args):
    from . import server
    server.serve(args.host, args.port)


def cmd_registry_add(args):
    from . import registry
    updated = registry.add(config.registry_path(), args.alias, args.reference)
    print(("updated " if updated else "added ") + args.alias, file=sys.stderr)


_RULE = "─" * 56


def _ask(prompt):
    """Write the prompt to stderr, read a line from stdin. '' on EOF."""
    sys.stderr.write(prompt)
    sys.stderr.flush()
    try:
        return input().strip()
    except EOFError:
        return ""


def _prune_reason(prune):
    if prune["kind"] == "item":
        return f'the 1Password item "{prune["item"]}" no longer exists in the vault'
    return f'the field "{prune["field"]}" no longer exists in item "{prune["item"]}"'


def cmd_registry_sync(args):
    from . import registry, sync

    current = config.load_registry()
    vaults = args.vault or sync.vaults_in_registry(current)
    if not vaults:
        raise FfSecretsError("no vault to sync (registry empty and no --vault given)")

    driver = config.build_driver()
    contents = {vault: driver.list_items(vault) for vault in vaults}

    def eligible(field):
        # Secrets live in CONCEALED fields with a value; everything else
        # (notes, usernames, dates, urls) is structural noise.
        return field["has_value"] and field["type"] == "CONCEALED"

    found = sync.discover(current, contents, eligible)
    out = sys.stderr

    namespaces = sync.item_namespaces(current)
    total = sum(len(items) for items in contents.values())
    known = sum(1 for vault, items in contents.items()
                for entry in items if (vault, entry["item"]) in namespaces)
    label = ", ".join(f'"{vault}"' for vault in vaults)
    print(f'\nScanning vault {label}… {total} items, {known} already mapped.', file=out)

    for warning in found["warnings"]:
        print(f"warning: {warning}", file=out)

    can_ask = sys.stdin.isatty() and not args.dry_run
    taken = set(current) | {alias for alias, _ in found["auto_adds"]}
    chosen_adds = []

    for entry in found["new_items"]:
        item = entry["item"]
        fields = entry["fields"]
        names = ", ".join(name for name, _ in fields)
        print(f"\n▸ In the vault but NOT in the registry yet:\n", file=out)
        print(f"    1Password item:  {item}", file=out)
        print(f"    Secret field{'s' if len(fields) != 1 else ''}:   {names}", file=out)
        print(f"\n    An alias is  <prefix>.<field>  — e.g.  hootsuite.slack.credential, bear.iphone.credential", file=out)
        print(f"    You pick the prefix; the field name is appended for you.", file=out)
        if not can_ask:
            note = "would prompt for a prefix" if args.dry_run else "no terminal to ask for a prefix; skipped"
            print(f"    ({note})", file=out)
            continue
        suggested = sync.slugify(item)
        prefix = _ask(f"\n    Prefix for this item  (Enter to skip · suggested: {suggested})\n    > ")
        if not prefix:
            continue
        for name, _ref in fields:
            slug = sync.slugify(name)
            if prefix == slug or prefix.endswith("." + slug):
                print(f'    note: the field name is appended automatically, so this becomes "{prefix}.{slug}".', file=out)
                break
        adds_here = []
        for name, reference in fields:
            alias = f"{prefix}.{sync.slugify(name)}"
            if alias in taken:
                print(f'    skipped "{alias}" (already exists)', file=out)
                continue
            taken.add(alias)
            adds_here.append((alias, reference))
        if adds_here:
            width = max(len(alias) for alias, _ in adds_here)
            print(f"\n    Will add:", file=out)
            for alias, reference in adds_here:
                print(f"      {alias.ljust(width)}  →  {reference}", file=out)
            chosen_adds.extend(adds_here)

    all_adds = found["auto_adds"] + chosen_adds
    prunes = found["prunes"]
    if not all_adds and not prunes:
        print("\nRegistry already in sync; nothing to do.", file=out)
        return

    print(f"\n{_RULE}\nPLANNED CHANGES", file=out)
    if all_adds:
        width = max(len(alias) for alias, _ in all_adds)
        print(f"\n  ADD ({len(all_adds)})", file=out)
        for alias, reference in all_adds:
            print(f"    + {alias.ljust(width)}  →  {reference}", file=out)
    if prunes:
        print(f"\n  REMOVE ({len(prunes)})", file=out)
        for prune in prunes:
            print(f"    − {prune['alias']}", file=out)
            print(f"        {_prune_reason(prune)}", file=out)

    if args.dry_run:
        print("\n(dry run; registry unchanged)", file=out)
        return
    if not args.yes:
        if not sys.stdin.isatty():
            print("\nnon-interactive and --yes not given; registry unchanged.", file=out)
            return
        answer = _ask(f"\n{_RULE}\nApply {len(all_adds)} addition(s) and {len(prunes)} removal(s)?  [y/N] ")
        if answer.lower() not in ("y", "yes"):
            print("Aborted; registry unchanged.", file=out)
            return

    prune_rows = [(prune["alias"], prune["reference"], prune["kind"]) for prune in prunes]
    registry.apply_changes(config.registry_path(), all_adds, prune_rows)
    print(f"\nRegistry updated: +{len(all_adds)} −{len(prunes)}.", file=out)


def build_parser():
    parser = argparse.ArgumentParser(prog="ff-secrets", description="Unified access to secrets.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("read", help="print the value of an alias")
    p.add_argument("alias")
    p.add_argument("-n", "--newline", action="store_true", help="append a trailing newline")
    p.set_defaults(func=cmd_read)

    p = sub.add_parser("list", help="list registry aliases")
    p.add_argument("prefix", nargs="?", default="", help="filter by prefix")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("run", help="run a command with secrets injected as env vars")
    p.add_argument("--env", action="append", metavar="VAR=alias", help="repeatable")
    p.add_argument("--env-file", metavar="FILE", help="lines of VAR=alias")
    p.add_argument("command", nargs=argparse.REMAINDER)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("inject", help="resolve ffsec:<alias> markers in a template")
    p.add_argument("-i", "--input", metavar="FILE", help="default: stdin")
    p.add_argument("-o", "--output", metavar="FILE", help="default: stdout")
    p.set_defaults(func=cmd_inject)

    p = sub.add_parser("serve", help="run the read-only HTTP API")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8666)
    p.set_defaults(func=cmd_serve)

    pr = sub.add_parser("registry", help="manage the alias registry")
    rsub = pr.add_subparsers(dest="registry_cmd", required=True)
    pa = rsub.add_parser("add", help="add or update an alias -> reference")
    pa.add_argument("alias")
    pa.add_argument("reference")
    pa.set_defaults(func=cmd_registry_add)

    psy = rsub.add_parser("sync", help="reconcile the registry with the backend vault")
    psy.add_argument("--vault", action="append", metavar="TITLE",
                     help="vault to enumerate (repeatable; default: those used by the registry)")
    psy.add_argument("--dry-run", action="store_true", help="show the plan without writing")
    psy.add_argument("-y", "--yes", action="store_true", help="apply without the confirmation prompt")
    psy.set_defaults(func=cmd_registry_sync)

    return parser


def main():
    args = build_parser().parse_args()
    try:
        args.func(args)
    except FfSecretsError as err:
        print(f"ff-secrets: {err}", file=sys.stderr)
        sys.exit(1)
