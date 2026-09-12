"""Dual-stack entry point: `python -m learning_service.serve`.

uvicorn's `--host ::` is IPv6-only because asyncio sets IPV6_V6ONLY on the
listening socket. Railway's private network needs IPv6, everything else
(compose, laptops, health probes) speaks IPv4, so bind one dual-stack socket
here and hand it to uvicorn.

`LEARNING_SEED=<scenario>` (spec §Deployment, KATA-4 R6) loads a golden
scenario once, before the server starts accepting traffic — the same
`learning_service.seed` module `python -m learning_service.seed ferry` runs
by hand. Idempotent (`seed.seed_ferry`'s own marker check), so leaving the
variable set across restarts is safe, not a re-seed every boot.
"""

from __future__ import annotations

import asyncio
import os
import socket

import uvicorn

from learning_service import seed as seed_module


def dual_stack_socket(port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
    sock.bind(("::", port))
    sock.listen(128)
    sock.set_inheritable(True)
    return sock


def run(sock: socket.socket, *, block: bool = True) -> uvicorn.Server:
    config = uvicorn.Config(
        "learning_service.main:app",
        fd=sock.fileno(),
        log_level=os.environ.get("LOG_LEVEL", "info").lower(),
        proxy_headers=True,
    )
    server = uvicorn.Server(config)
    if block:
        server.run(sockets=[sock])
    return server


def main() -> None:
    scenario = os.environ.get("LEARNING_SEED")
    if scenario:
        asyncio.run(seed_module._run(scenario))
    port = int(os.environ.get("PORT", "8000"))
    run(dual_stack_socket(port))


if __name__ == "__main__":
    main()
