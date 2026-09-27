"""Short-lived HTTPS CONNECT proxy for dependency downloads; never runs submission code."""

import base64
import ipaddress
import json
import os
import select
import socket
import socketserver
import ssl
import threading
from urllib.parse import unquote, urlsplit


def public_addresses(host):
    addresses = list(
        dict.fromkeys(item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM))
    )
    if not addresses or any(
        not ipaddress.ip_address(address).is_global or ipaddress.ip_address(address).is_multicast
        for address in addresses
    ):
        raise ValueError("Dependency hosts must resolve to public Internet addresses")
    return addresses


def header(stream):
    data = bytearray()
    while not data.endswith(b"\r\n\r\n"):
        chunk = stream.recv(1)
        if not chunk or len(data) >= 16384:
            raise ValueError("Invalid proxy request")
        data.extend(chunk)
    return bytes(data)


def connect(host, upstream):
    addresses = public_addresses(host)
    last_error = None
    for address in addresses:
        stream = None
        try:
            if not upstream:
                return socket.create_connection((address, 443), timeout=10)
            proxy = urlsplit(upstream)
            if proxy.scheme not in ("http", "https") or not proxy.hostname:
                raise ValueError("Dependency upstream proxy must use HTTP or HTTPS")
            stream = socket.create_connection(
                (proxy.hostname, proxy.port or (443 if proxy.scheme == "https" else 80)), timeout=10
            )
            if proxy.scheme == "https":
                stream = ssl.create_default_context().wrap_socket(
                    stream, server_hostname=proxy.hostname
                )
            target = f"[{address}]:443" if ":" in address else f"{address}:443"
            request = f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n"
            if proxy.username is not None:
                credentials = f"{unquote(proxy.username)}:{unquote(proxy.password or '')}"
                token = base64.b64encode(credentials.encode()).decode()
                request += f"Proxy-Authorization: Basic {token}\r\n"
            stream.sendall((request + "\r\n").encode())
            if header(stream).split(b" ", 2)[1] != b"200":
                raise OSError("Upstream proxy refused the connection")
            return stream
        except (OSError, ValueError, IndexError) as exc:
            if stream is not None:
                stream.close()
            last_error = exc
    raise OSError("Could not connect to dependency host") from last_error


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        if not self.server.slots.acquire(blocking=False):
            return
        try:
            self.request.settimeout(10)
            request = header(self.request).split(b"\r\n", 1)[0].decode("ascii")
            method, target, version = request.split(" ")
            host, port = target.rsplit(":", 1)
            host = host.lower()
            if (
                method != "CONNECT"
                or version not in ("HTTP/1.0", "HTTP/1.1")
                or port != "443"
                or host not in self.server.hosts
            ):
                self.request.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
                return
            with connect(host, self.server.upstream) as destination:
                self.request.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
                streams = [self.request, destination]
                while True:
                    readable = [s for s in streams if isinstance(s, ssl.SSLSocket) and s.pending()]
                    if not readable:
                        readable = select.select(streams, [], [], 30)[0]
                    if not readable:
                        return
                    for source in readable:
                        chunk = source.recv(65536)
                        if not chunk:
                            return
                        (destination if source is self.request else self.request).sendall(chunk)
        except (OSError, ValueError, UnicodeError):
            try:
                self.request.sendall(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
            except OSError:
                pass
        finally:
            self.server.slots.release()


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address, hosts, upstream=""):
        self.hosts = frozenset(hosts)
        self.upstream = upstream
        self.slots = threading.BoundedSemaphore(32)
        super().__init__(address, Handler)


if __name__ == "__main__":
    # Bind only the isolated network interface, never the outward-facing bridge interface.
    with Server(
        (os.environ["OJ_DEPENDENCY_BIND"], 3128),
        json.loads(os.environ["OJ_DEPENDENCY_HOSTS"]),
        os.environ.get("OJ_DEPENDENCY_PROXY", ""),
    ) as server:
        server.serve_forever()
