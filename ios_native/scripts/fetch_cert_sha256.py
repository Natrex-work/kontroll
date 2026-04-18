#!/usr/bin/env python3
"""Fetch the leaf TLS certificate for a host and print its SHA-256 digest.

Example:
    python3 fetch_cert_sha256.py kontroll.example.no
    python3 fetch_cert_sha256.py kontroll.example.no --port 443 --format both
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import socket
import ssl
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch server certificate SHA-256 for optional iOS pinning.")
    parser.add_argument("host", help="Host name, for example kontroll.example.no")
    parser.add_argument("--port", type=int, default=443, help="TLS port, default 443")
    parser.add_argument("--format", choices=["hex", "base64", "both"], default="both")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    context = ssl.create_default_context()
    with socket.create_connection((args.host, args.port), timeout=10) as sock:
        with context.wrap_socket(sock, server_hostname=args.host) as tls:
            cert = tls.getpeercert(binary_form=True)
            if not cert:
                raise RuntimeError("No certificate received from server")
    digest = hashlib.sha256(cert).digest()
    hex_digest = digest.hex()
    b64_digest = base64.b64encode(digest).decode("ascii")

    print(f"Host:      {args.host}:{args.port}")
    if args.format in {"hex", "both"}:
        print(f"SHA256 hex:    {hex_digest}")
    if args.format in {"base64", "both"}:
        print(f"SHA256 base64: {b64_digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
