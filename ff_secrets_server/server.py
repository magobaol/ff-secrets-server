"""HTTP surface: read-only alias -> value over the network.

Auth is network-level (deployment binds/firewalls this); no application token.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

from . import config
from .errors import FfSecretsError


def make_handler(core):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status, body):
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            parsed = urlparse(self.path)
            parts = [p for p in parsed.path.split("/") if p]
            if len(parts) == 3 and parts[:2] == ["v1", "secret"]:
                try:
                    self._send(200, core.read(unquote(parts[2])))
                except FfSecretsError as e:
                    self._send(404, f"{e}\n")
                except Exception as e:
                    self._send(500, f"{e}\n")
            elif parts == ["v1", "aliases"]:
                prefix = parse_qs(parsed.query).get("prefix", [""])[0]
                self._send(200, "\n".join(core.aliases(prefix)) + "\n")
            else:
                self._send(404, "not found\n")

        def log_message(self, *a):
            pass

    return Handler


def serve(host, port):
    httpd = ThreadingHTTPServer((host, port), make_handler(config.build_core()))
    httpd.serve_forever()
