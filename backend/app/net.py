"""Prefer IPv4 for outgoing connections.

On networks where IPv6 is advertised but not routed (common on home/campus Wi-Fi), every new
connection to Supabase first waits for the IPv6 attempts to time out (~40 s) before falling back
to IPv4. Resolving to IPv4 only removes that wait. Set PREFER_IPV4=false to disable.
"""
from __future__ import annotations

import os
import socket

_original = socket.getaddrinfo


def _ipv4_first(host, port, family=0, *args, **kwargs):
    results = _original(host, port, family, *args, **kwargs)
    ipv4 = [r for r in results if r[0] == socket.AF_INET]
    return ipv4 or results


if os.getenv("PREFER_IPV4", "true").strip().lower() not in ("0", "false", "no", "off") \
        and socket.getaddrinfo is _original:
    socket.getaddrinfo = _ipv4_first
