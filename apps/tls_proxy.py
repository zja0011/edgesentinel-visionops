"""Bounded HTTPS reverse proxy for the local EdgeSentinel HTTP API."""

import argparse
import http.client
import os
import socketserver
import ssl
import stat
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer


HOP_BY_HOP_HEADERS = frozenset(
    (
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "proxy-connection",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    )
)
MAX_REQUEST_BYTES = 2 * 1024 * 1024
BUFFER_BYTES = 64 * 1024


def filtered_headers(headers, response=False):
    result = []
    for name, value in headers:
        lowered = str(name).strip().lower()
        if lowered in HOP_BY_HOP_HEADERS:
            continue
        if response and lowered in ("server", "date"):
            continue
        if not response and lowered in (
            "host",
            "x-forwarded-for",
            "x-forwarded-host",
            "x-forwarded-proto",
        ):
            continue
        result.append((str(name), str(value)))
    return result


def validate_tls_file(path, private=False):
    path = os.path.abspath(str(path or ""))
    try:
        metadata = os.lstat(path)
    except OSError as error:
        raise ValueError("TLS file is unavailable") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ValueError("TLS path must be a regular non-symlink file")
    if private and stat.S_IMODE(metadata.st_mode) & 0o077:
        raise ValueError("TLS private key permissions are too broad")
    if metadata.st_size <= 0 or metadata.st_size > 1024 * 1024:
        raise ValueError("TLS file size is invalid")
    return path


class ThreadedHttpServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class TlsProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "EdgeSentinelTLS/1.0"
    sys_version = ""

    def do_GET(self):
        self._proxy()

    def do_HEAD(self):
        self._proxy()

    def do_POST(self):
        self._proxy()

    def do_PUT(self):
        self._proxy()

    def do_DELETE(self):
        self._proxy()

    def do_PATCH(self):
        self._proxy()

    def do_OPTIONS(self):
        self._proxy()

    def log_message(self, template, *arguments):
        # Do not log URLs, query strings, cookies, or request bodies.
        return

    def _proxy(self):
        length_text = self.headers.get("Content-Length")
        if self.headers.get("Transfer-Encoding"):
            self.send_error(400, "chunked request bodies are unsupported")
            return
        try:
            content_length = int(length_text or "0")
        except ValueError:
            self.send_error(400, "invalid content length")
            return
        if content_length < 0 or content_length > MAX_REQUEST_BYTES:
            self.send_error(413, "request body is too large")
            return
        body = self.rfile.read(content_length) if content_length else None
        connection = http.client.HTTPConnection(
            self.server.upstream_host,
            self.server.upstream_port,
            timeout=self.server.upstream_timeout,
        )
        headers = dict(filtered_headers(self.headers.items()))
        headers["Host"] = "{0}:{1}".format(
            self.server.upstream_host,
            self.server.upstream_port,
        )
        headers["X-Forwarded-Proto"] = "https"
        headers["X-Forwarded-Host"] = str(
            self.headers.get("Host") or ""
        )[:255]
        try:
            connection.request(self.command, self.path, body, headers)
            upstream = connection.getresponse()
            self.send_response(upstream.status, upstream.reason)
            response_headers = filtered_headers(
                upstream.getheaders(), response=True
            )
            has_length = any(
                name.lower() == "content-length"
                for name, unused in response_headers
            )
            for name, value in response_headers:
                self.send_header(name, value)
            if not has_length:
                self.send_header("Connection", "close")
                self.close_connection = True
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Strict-Transport-Security", "max-age=31536000"
            )
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; img-src 'self' data:; "
                "style-src 'self'; script-src 'self'; "
                "connect-src 'self'; frame-ancestors 'none'; "
                "base-uri 'none'; form-action 'self'",
            )
            self.end_headers()
            if self.command != "HEAD":
                while True:
                    chunk = upstream.read(BUFFER_BYTES)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()
        except (OSError, http.client.HTTPException):
            if not self.wfile.closed:
                try:
                    self.send_error(502, "local API is unavailable")
                except OSError:
                    pass
        finally:
            connection.close()


def build_server(
    listen_host,
    listen_port,
    upstream_host,
    upstream_port,
    certificate,
    private_key,
    upstream_timeout=90.0,
):
    if upstream_host not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("TLS proxy upstream must be loopback")
    certificate = validate_tls_file(certificate)
    private_key = validate_tls_file(private_key, private=True)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    if hasattr(ssl, "OP_NO_TLSv1"):
        context.options |= ssl.OP_NO_TLSv1
    if hasattr(ssl, "OP_NO_TLSv1_1"):
        context.options |= ssl.OP_NO_TLSv1_1
    context.load_cert_chain(certificate, private_key)
    server = ThreadedHttpServer(
        (listen_host, int(listen_port)), TlsProxyHandler
    )
    server.upstream_host = upstream_host
    server.upstream_port = int(upstream_port)
    server.upstream_timeout = max(
        5.0, min(float(upstream_timeout), 120.0)
    )
    server.socket = context.wrap_socket(
        server.socket, server_side=True
    )
    return server


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen-host", default="0.0.0.0")
    parser.add_argument("--listen-port", type=int, default=8443)
    parser.add_argument("--upstream-host", default="127.0.0.1")
    parser.add_argument("--upstream-port", type=int, default=8000)
    parser.add_argument("--certificate", required=True)
    parser.add_argument("--private-key", required=True)
    arguments = parser.parse_args(argv)
    server = build_server(
        arguments.listen_host,
        arguments.listen_port,
        arguments.upstream_host,
        arguments.upstream_port,
        arguments.certificate,
        arguments.private_key,
    )
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
