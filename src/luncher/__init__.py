"""Luncher - Daily lunch menu aggregator for Czech restaurants."""

__version__ = "0.1.0"

# Some restaurant hosts advertise IPv6 (AAAA) records that aren't actually
# routable from GitHub Actions runners, causing "Network is unreachable"
# (ENETUNREACH) even though the same host works fine over IPv4. Force
# requests/urllib3 to resolve and connect over IPv4 only, process-wide.
import socket
import urllib3.util.connection as _urllib3_connection

_urllib3_connection.allowed_gai_family = lambda: socket.AF_INET
