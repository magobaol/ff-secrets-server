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


def cmd_registry_sync(args):
    from . import registry, sync

    current = config.load_registry()
    vaults = args.vault or sync.vaults_in_registry(current)
    if not vaults:
        raise FfSecretsError("no vault to sync (registry empty and no --vault given)")

    driver = config.build_driver()
    contents = {vault: driver.list_items(vault) for vault in vaults}

    can_ask = sys.stdin.isatty()

    def ask_namespace(vault, item, field):
        head = f"new item not in the registry:\n  vault: {vault}\n  item : {item}\n  field: {field}"
        if args.dry_run:
            print(head + "\n  (would prompt for a namespace)", file=sys.stderr)
            return ""
        if not can_ask:
            print(head + "\n  ! skipped (no namespace, non-interactive)", file=sys.stderr)
            return ""
        sys.stderr.write(head + "\n  namespace for this item (e.g. 'hootsuite.slack'), empty to skip: ")
        sys.stderr.flush()
        return input().strip()

    def eligible(field):
        # Secrets live in CONCEALED fields with a value; everything else
        # (notes, usernames, dates, urls) is structural noise.
        return field["has_value"] and field["type"] == "CONCEALED"

    adds, prunes, warnings = sync.plan(current, contents, ask_namespace, eligible)

    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    if not adds and not prunes:
        print("registry already in sync; nothing to do.", file=sys.stderr)
        return

    print("\nplanned changes:", file=sys.stderr)
    for alias, reference in adds:
        print(f"  + {alias}  ->  {reference}", file=sys.stderr)
    for alias, _reference, reason in prunes:
        print(f"  - {alias}  ({reason})", file=sys.stderr)

    if args.dry_run:
        print("\ndry run; registry unchanged.", file=sys.stderr)
        return
    if not args.yes:
        if not can_ask:
            print("\nnon-interactive and --yes not given; registry unchanged.", file=sys.stderr)
            return
        sys.stderr.write(f"\napply {len(adds)} add(s) and {len(prunes)} prune(s)? [y/N] ")
        sys.stderr.flush()
        if input().strip().lower() not in ("y", "yes"):
            print("aborted; registry unchanged.", file=sys.stderr)
            return

    registry.apply_changes(config.registry_path(), adds, prunes)
    print(f"registry updated: +{len(adds)} -{len(prunes)}", file=sys.stderr)


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
