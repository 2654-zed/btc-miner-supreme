"""
stratum_submitter.py
────────────────────
Stratum V1 protocol client for pool-based mining.

Implements the essential subset of the Stratum protocol:
  - mining.subscribe
  - mining.authorize
  - mining.notify  (server → client)
  - mining.submit  (client → server)

The client maintains a persistent TCP socket (optionally TLS) with
automatic reconnection to the primary pool and failover to backup pools.
"""

from __future__ import annotations

import json
import logging
import socket
import ssl
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class StratumJob:
    """Represents a mining.notify job from the pool."""
    job_id: str
    prev_hash: str
    coinb1: str
    coinb2: str
    merkle_branches: List[str]
    version: str
    nbits: str
    ntime: str
    clean_jobs: bool


@dataclass
class StratumConfig:
    pool_url: str = ""  # REQUIRED — must be set explicitly
    worker: str = "miner_supreme.001"
    password: str = ""  # REQUIRED — set via config.yaml or STRATUM_PASSWORD env
    backup_pools: List[str] = field(default_factory=list)
    connect_timeout: int = 15
    read_timeout: int = 60
    reconnect_delay: float = 5.0
    use_tls: bool = False


class StratumSubmitter:
    """
    Stratum V1 client with subscribe / authorize / submit lifecycle.
    """

    def __init__(
        self,
        pool_url: str = "",
        worker: str = "miner_supreme.001",
        password: str = "",
        backup_pools: Optional[List[str]] = None,
    ) -> None:
        if not pool_url or "example.com" in pool_url:
            raise ValueError(
                f"Invalid pool_url '{pool_url}'. "
                "Provide a real Stratum pool URL (e.g. stratum+tcp://pool.braiins.com:3333)."
            )
        self.pool_url = pool_url
        self.worker = worker
        self.password = password
        self.backup_pools = backup_pools or []

        self._sock: Optional[socket.socket] = None
        self._lock = threading.Lock()
        self._msg_id = 0
        self._subscribed = False
        self._authorized = False
        self._current_job: Optional[StratumJob] = None
        self._extranonce1: str = ""
        self._extranonce2_size: int = 4
        self._on_notify: Optional[Callable[[StratumJob], None]] = None

        self._reader_thread: Optional[threading.Thread] = None
        self._running = False

        logger.info("StratumSubmitter → %s  worker=%s", pool_url, worker)

    # ── Connection ───────────────────────────────────────────────────────
    def _parse_url(self, url: str) -> Tuple[str, int, bool]:
        """Parse 'stratum+tcp://host:port' into (host, port, tls)."""
        use_tls = "ssl" in url or "tls" in url
        clean = url.replace("stratum+tcp://", "").replace("stratum+ssl://", "")
        clean = clean.replace("stratum+tls://", "")
        host, port_str = clean.rsplit(":", 1)
        return host, int(port_str), use_tls

    def connect(self) -> bool:
        """Connect, subscribe, and authorize."""
        urls = [self.pool_url] + self.backup_pools
        for url in urls:
            try:
                host, port, use_tls = self._parse_url(url)
                logger.info("Connecting to %s:%d (TLS=%s)", host, port, use_tls)
                raw = socket.create_connection((host, port), timeout=15)
                if use_tls:
                    ctx = ssl.create_default_context()
                    raw = ctx.wrap_socket(raw, server_hostname=host)
                self._sock = raw
                self._subscribe()
                self._authorize()
                self._start_reader()
                logger.info("Stratum connected and authorised")
                return True
            except Exception as exc:
                logger.warning("Failed to connect to %s: %s", url, exc)
                continue
        logger.error("All pool connections failed")
        return False

    def disconnect(self) -> None:
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    # ── Protocol messages ────────────────────────────────────────────────
    def _send(self, method: str, params: list) -> int:
        with self._lock:
            self._msg_id += 1
            msg = {
                "id": self._msg_id,
                "method": method,
                "params": params,
            }
            raw = json.dumps(msg) + "\n"
            self._sock.sendall(raw.encode())
            return self._msg_id

    def _recv_line(self) -> str:
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = self._sock.recv(4096)
            if not chunk:
                raise ConnectionError("Connection closed")
            buf += chunk
        return buf.decode().strip()

    def _recv_json(self) -> Dict:
        return json.loads(self._recv_line())

    # ── Subscribe ────────────────────────────────────────────────────────
    def _subscribe(self) -> None:
        self._send("mining.subscribe", ["btc-miner-supreme/1.0"])
        resp = self._recv_json()
        result = resp.get("result", [])
        if len(result) >= 3:
            self._extranonce1 = result[1]
            self._extranonce2_size = result[2]
        self._subscribed = True
        logger.debug("Subscribed: extranonce1=%s  en2_size=%d",
                      self._extranonce1, self._extranonce2_size)

    # ── Authorize ────────────────────────────────────────────────────────
    def _authorize(self) -> None:
        self._send("mining.authorize", [self.worker, self.password])
        resp = self._recv_json()
        if resp.get("result") is True:
            self._authorized = True
        else:
            raise RuntimeError(f"Authorization failed: {resp}")

    # ── Submit nonce ─────────────────────────────────────────────────────
    def submit(
        self,
        nonce: int,
        job_id: Optional[str] = None,
        extranonce2: Optional[str] = None,
        ntime: Optional[str] = None,
    ) -> bool:
        """
        Submit a found nonce to the pool.

        Parameters
        ----------
        nonce : int
            The winning nonce value.
        job_id : str, optional
            Pool job ID (from mining.notify). Uses current job if None.
        extranonce2 : str, optional
            Hex extranonce2 value. Auto-generated if None.
        ntime : str, optional
            Block time. Uses current job ntime if None.
        """
        job = self._current_job
        if job is None and job_id is None:
            logger.error("No active job — cannot submit")
            return False

        _job_id = job_id or (job.job_id if job else "")
        _ntime = ntime or (job.ntime if job else "")
        _en2 = extranonce2 or ("00" * self._extranonce2_size)
        nonce_hex = f"{nonce:08x}"

        msg_id = self._send("mining.submit", [
            self.worker, _job_id, _en2, _ntime, nonce_hex,
        ])
        logger.info("Submitted nonce %s for job %s (msg_id=%d)", nonce_hex, _job_id, msg_id)
        return True

    # ── Background reader ────────────────────────────────────────────────
    def _start_reader(self) -> None:
        self._running = True
        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()

    def _read_loop(self) -> None:
        while self._running:
            try:
                line = self._recv_line()
                msg = json.loads(line)
                self._handle_message(msg)
            except Exception as exc:
                if self._running:
                    logger.warning("Stratum read error: %s", exc)
                break

    def _handle_message(self, msg: Dict) -> None:
        method = msg.get("method")
        if method == "mining.notify":
            params = msg.get("params", [])
            if len(params) >= 9:
                job = StratumJob(
                    job_id=params[0],
                    prev_hash=params[1],
                    coinb1=params[2],
                    coinb2=params[3],
                    merkle_branches=params[4],
                    version=params[5],
                    nbits=params[6],
                    ntime=params[7],
                    clean_jobs=params[8],
                )
                self._current_job = job
                logger.debug("New job: %s  clean=%s", job.job_id, job.clean_jobs)
                if self._on_notify:
                    self._on_notify(job)

        elif method == "mining.set_difficulty":
            diff = msg.get("params", [1])[0]
            logger.info("Pool difficulty set to %s", diff)

        elif "id" in msg and "result" in msg:
            # Response to our submission
            if msg.get("result") is True:
                logger.info("Share accepted (id=%s)", msg["id"])
            elif msg.get("error"):
                logger.warning("Share rejected (id=%s): %s", msg["id"], msg["error"])

    # ── Properties ───────────────────────────────────────────────────────
    @property
    def current_job(self) -> Optional[StratumJob]:
        return self._current_job

    @property
    def is_connected(self) -> bool:
        return self._sock is not None and self._authorized

    def set_notify_callback(self, cb: Callable[[StratumJob], None]) -> None:
        self._on_notify = cb
