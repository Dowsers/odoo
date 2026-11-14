#!/usr/bin/env python3
"""Redirect every plain HTTP request to the HTTPS address of Odoo.

Old links such as http://<name>:8069/odoo/action-123 keep working: Tailscale
Serve forwards the plain HTTP ports to this service, which answers
"308 Permanent Redirect" to HTTPS_URL followed by the same path and query.

Environment:
    HTTPS_URL      required, e.g. https://odoo.example.ts.net
    REDIRECT_BIND  address to listen on (default 127.0.0.1)
    REDIRECT_PORT  port to listen on (default 8068)
"""
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

TARGET = os.environ.get('HTTPS_URL', '').rstrip('/')
_parts = urlsplit(TARGET)
if _parts.scheme != 'https' or not _parts.netloc or _parts.path or _parts.query or _parts.fragment:
    sys.exit("HTTPS_URL must look like https://odoo.example.ts.net")


class RedirectHandler(BaseHTTPRequestHandler):
    server_version = 'odoo-https-redirect'
    sys_version = ''
    protocol_version = 'HTTP/1.1'
    timeout = 15  # seconds: drop idle or stalled connections

    def redirect(self):
        # Only the path and the query of the request are reused, after the fixed HTTPS_URL:
        # the redirection can never leave the Odoo address.
        path = '/' + self.path.lstrip('/')
        self.send_response(308)
        self.send_header('Location', TARGET + path)
        self.send_header('Content-Length', '0')
        self.send_header('Connection', 'close')
        self.end_headers()
        self.close_connection = True

    do_GET = do_HEAD = do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = redirect

    def log_message(self, format, *args):  # noqa: A002 - signature of the base class
        pass


def main():
    address = (os.environ.get('REDIRECT_BIND', '127.0.0.1'), int(os.environ.get('REDIRECT_PORT', '8068')))
    server = ThreadingHTTPServer(address, RedirectHandler)
    server.daemon_threads = True
    print("redirecting http://%s:%s to %s" % (address[0], address[1], TARGET), flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
