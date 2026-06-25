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

    return parser


def main():
    args = build_parser().parse_args()
    try:
        args.func(args)
    except FfSecretsError as err:
        print(f"ff-secrets: {err}", file=sys.stderr)
        sys.exit(1)
