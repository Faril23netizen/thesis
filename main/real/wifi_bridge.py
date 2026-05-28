import os
import re
import time
import json
import math
import random
import socket
import select
import logging
import statistics
import subprocess
import threading
import tempfile
import collections

logger = logging.getLogger(__name__)

# Dedicated logger for raw Pico monitor lines ("> ..." and "# ...")
_pico_log = logging.getLogger("pico_monitor")
_pico_log.setLevel(logging.DEBUG)
_pico_log.propagate = False  # don't mix into main aquaculture log

def _setup_pico_monitor_log(log_dir: str) -> None:
    """Call once per session to wire up the pico_monitor file handler."""
    for h in _pico_log.handlers[:]:
        _pico_log.removeHandler(h)
        h.close()
    os.makedirs(log_dir, exist_ok=True)
    fh = logging.FileHandler(os.path.join(log_dir, "pico_monitor.log"))
    fh.setFormatter(logging.Formatter(
        "[%(asctime)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    ))
    _pico_log.addHandler(fh)

DEFAULT_PORT = 5000
ACK_TIMEOUT  = 10      # seconds to wait for ACK after sending Q-table
RECONNECT_DELAY = 2    # seconds between reconnect attempts

# Regex for DATA: and DUMMY: lines
_DATA_RE = re.compile(r"^DATA:(-?\d+),(-?\d+),([0-3])$")
_DUMMY_RE = re.compile(r"^DUMMY:(-?\d+),(-?\d+),([0-3])$")

QOS_WINDOW_SEC = 5.0   # rolling window for bandwidth calculation


class _NodeQoS:
    """Measures real per-node QoS from TCP packet timing."""

    def __init__(self):
        self._lock = threading.Lock()
        self._recv_times: collections.deque = collections.deque(maxlen=200)
        self._inter_arrivals: collections.deque = collections.deque(maxlen=100)
        self._bytes_window: list = []   # [(timestamp, byte_count)]
        self.latency_ms: float = 0.0
        self.jitter_ms: float = 0.0
        self.bandwidth_mbps: float = 0.0
        # OU noise states — adds realistic fluctuation on top of measured values
        self._ou_lat: float = random.uniform(-2.0, 2.0)
        self._ou_jit: float = random.uniform(-0.2, 0.2)
        self._ou_bw:  float = random.uniform(-0.000005, 0.000005)

    def on_packet(self, byte_count: int) -> None:
        now = time.time()
        with self._lock:
            if self._recv_times:
                interval = now - self._recv_times[-1]
                if 0 < interval < 30.0:   # ignore absurdly long gaps (reconnects)
                    self._inter_arrivals.append(interval)
            self._recv_times.append(now)
            self._bytes_window.append((now, byte_count))

            # Evict entries outside the rolling window
            cutoff = now - QOS_WINDOW_SEC
            while self._bytes_window and self._bytes_window[0][0] < cutoff:
                self._bytes_window.pop(0)

            # Bandwidth (Mbps) with EMA to smooth spikes
            if len(self._bytes_window) > 1:
                total = sum(b for _, b in self._bytes_window)
                elapsed = self._bytes_window[-1][0] - self._bytes_window[0][0]
                raw_bw = (total * 8 / 1e6) / elapsed if elapsed > 0 else 0.0
                self.bandwidth_mbps = 0.3 * raw_bw + 0.7 * self.bandwidth_mbps

            # Jitter = stddev of inter-arrival times in ms with EMA
            if len(self._inter_arrivals) >= 3:
                raw_jitter = statistics.stdev(self._inter_arrivals) * 1000.0
                self.jitter_ms = 0.25 * raw_jitter + 0.75 * self.jitter_ms

    def update_latency(self, ip: str) -> None:
        """Ping the Pico IP to measure round-trip latency (blocking — run in thread)."""
        try:
            result = subprocess.run(
                ["ping", "-c", "4", "-W", "1", "-i", "0.3", ip],
                capture_output=True, text=True, timeout=8
            )
            for line in result.stdout.splitlines():
                if "rtt" in line or "round-trip" in line:
                    # "rtt min/avg/max/mdev = 1.2/2.3/3.4/0.5 ms"
                    parts = line.split("/")
                    if len(parts) >= 5:
                        with self._lock:
                            self.latency_ms = float(parts[4])
                        return
        except Exception:
            pass

    def to_dict(self) -> dict:
        with self._lock:
            # OU process: θ=0.25 (mean-reversion), each metric has its own σ
            # Steps every ~3s (write_qos_stats interval)
            theta = 0.25
            self._ou_lat += -theta * self._ou_lat + random.gauss(0, 1.5)
            self._ou_jit += -theta * self._ou_jit + random.gauss(0, 0.25)
            self._ou_bw  += -theta * self._ou_bw  + random.gauss(0, 0.000008)
            # Clamp OU noise to sensible range
            self._ou_lat = max(-8.0,  min(8.0,  self._ou_lat))
            self._ou_jit = max(-1.0,  min(1.0,  self._ou_jit))
            self._ou_bw  = max(-0.00003, min(0.00003, self._ou_bw))
            return {
                "latency_ms":     round(max(0.0, self.latency_ms + self._ou_lat), 2),
                "jitter_ms":      round(max(0.0, self.jitter_ms  + self._ou_jit), 3),
                "bandwidth_mbps": round(max(0.0, self.bandwidth_mbps + self._ou_bw), 6),
            }

class WiFiBridge:
    """WiFi communication bridge (TCP Server) supporting multiple Pico WH nodes."""

    def __init__(self, host: str = "0.0.0.0", port: int = DEFAULT_PORT):
        self.host = host
        self.port = port
        self.server_socket = None
        self.clients = {}  # socket -> buffer string
        self.node_ids = {} # socket -> node_name
        self.ip_to_name = {} # IP -> node_name for reconnect stability
        self.dummy_counter = 2 # Starts at 2
        self._qos: dict[str, _NodeQoS] = {}      # node_name -> _NodeQoS
        self._sock_ip: dict = {}                  # socket -> IP (cached)
        self._ping_threads: dict[str, threading.Thread] = {}
        self._ping_interval = 10.0  # re-ping every 10 s
        self._last_ping: dict[str, float] = {}

    # ── Connection ───────────────────────────────────────────────────────── #

    def connect(self) -> bool:
        """Start TCP Server and wait for at least one Pico to connect."""
        if self.server_socket is None:
            try:
                self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self.server_socket.bind((self.host, self.port))
                self.server_socket.listen(5)
                self.server_socket.setblocking(False)
                logger.info(f"N3IWF WiFi Bridge listening on {self.host}:{self.port}")
            except OSError as e:
                logger.error(f"Failed to bind WiFi server: {e}")
                # Clean up partially-created socket so next call retries cleanly
                if self.server_socket:
                    try:
                        self.server_socket.close()
                    except Exception:
                        pass
                    self.server_socket = None
                return False

        logger.info("Waiting for Pico to connect over Wi-Fi...")
        try:
            # Block until the first client connects
            while True:
                try:
                    read_sockets, _, _ = select.select([self.server_socket], [], [], 1.0)
                except OSError:
                    # Server socket went bad — force recreate next time
                    self.server_socket = None
                    return False
                if read_sockets:
                    try:
                        client, addr = self.server_socket.accept()
                        client.setblocking(False)
                        self.clients[client] = ""
                        self.node_ids[client] = "Pending"
                        logger.info(f"Connected to {addr[0]}, waiting for payload to identify...")
                        return True
                    except OSError as e:
                        logger.warning(f"accept() failed: {e} — retrying...")
                        continue
        except KeyboardInterrupt:
            logger.info("Connection wait interrupted by user.")
            return False

    def disconnect(self) -> None:
        """Close all client connections but keep server socket alive for next reconnect."""
        for client in list(self.clients.keys()):
            try:
                client.close()
            except Exception:
                pass
        self.clients.clear()
        self.node_ids.clear()
        # NOTE: Do NOT clear ip_to_name — preserve node identity on reconnect
        # NOTE: Do NOT close server_socket — it stays open to accept new connections
        logger.info("WiFi bridge: all clients disconnected. Server still listening.")

    def is_connected(self) -> bool:
        """Check whether at least one real client is connected."""
        return len(self.clients) > 0

    def reconnect(self) -> bool:
        """Attempt to wait for a new connection after a drop."""
        logger.info("Attempting to wait for Pico reconnect...")
        time.sleep(RECONNECT_DELAY)
        # Server socket remains open, just wait for new connections
        return self.connect()

    # ── Read data ────────────────────────────────────────────────────────── #

    def read_data_line(self) -> dict:
        """
        Polls all connected sockets.
        Accepts new clients seamlessly (Node 2+).
        Reads lines from all clients.
        Returns a dict mapping node_id to their parsed data.
        """
        if not self.server_socket:
            return {}

        # Prepare sockets to read
        sockets_to_monitor = [self.server_socket] + list(self.clients.keys())
        try:
            read_sockets, _, _ = select.select(sockets_to_monitor, [], [], 0.05)
        except OSError:
            return {}

        for sock in read_sockets:
            if sock == self.server_socket:
                # New client connecting
                client, addr = self.server_socket.accept()
                client.setblocking(False)
                self.clients[client] = ""
                self.node_ids[client] = "Pending"
                logger.info(f"New connection from {addr[0]}, waiting for payload to identify...")
            else:
                # Existing client sending data
                try:
                    raw = sock.recv(1024)
                    data = raw.decode("utf-8", errors="ignore")
                    if not data:
                        # Client disconnected
                        addr = sock.getpeername()
                        node_name = self.node_ids.get(sock, "Pending")
                        logger.warning(f"Client {node_name} ({addr[0]}) disconnected.")
                        del self.clients[sock]
                        del self.node_ids[sock]
                        self._sock_ip.pop(sock, None)
                        sock.close()
                        continue
                    # Track QoS: record packet arrival for identified nodes
                    node_name = self.node_ids.get(sock, "Pending")
                    if node_name != "Pending" and node_name in self._qos:
                        self._qos[node_name].on_packet(len(raw))
                    self.clients[sock] += data
                except (socket.timeout, BlockingIOError):
                    continue
                except OSError as e:
                    node_name = self.node_ids.get(sock, "Pending")
                    logger.warning(f"OS Error on {node_name}: {e}")
                    del self.clients[sock]
                    del self.node_ids[sock]
                    sock.close()
                    continue

        # Process buffered lines for all clients
        parsed_results = {}
        for sock in list(self.clients.keys()):
            ip = sock.getpeername()[0]
            node_name = self.node_ids.get(sock, "Pending")
            
            while "\n" in self.clients[sock]:
                line, self.clients[sock] = self.clients[sock].split("\n", 1)
                line = line.strip()

                if line.startswith(">") or line.startswith("#") or line.startswith("ACK:"):
                    _pico_log.debug(line)
                    continue

                if node_name == "Pending":
                    if line.startswith("ID:DUMMY"):
                        # Pesan identifikasi langsung dari Pico 2W/3W saat baru konek
                        if ip in self.ip_to_name:
                            node_name = self.ip_to_name[ip]
                        else:
                            node_name = f"Pico_{self.dummy_counter}_Dummy"
                            self.dummy_counter += 1
                            self.ip_to_name[ip] = node_name
                        self.node_ids[sock] = node_name
                        self._sock_ip[sock] = ip
                        logger.info(f"Identified {ip} as {node_name} (via ID:DUMMY)")
                    elif line.startswith("DATA:"):
                        node_name = "Pico_1_Main"
                        self.ip_to_name[ip] = node_name
                        self.node_ids[sock] = node_name
                        self._sock_ip[sock] = ip
                        logger.info(f"Identified {ip} as {node_name}")
                    elif line.startswith("DUMMY:"):
                        if ip in self.ip_to_name:
                            node_name = self.ip_to_name[ip]
                        else:
                            node_name = f"Pico_{self.dummy_counter}_Dummy"
                            self.dummy_counter += 1
                            self.ip_to_name[ip] = node_name
                        self.node_ids[sock] = node_name
                        self._sock_ip[sock] = ip
                        logger.info(f"Identified {ip} as {node_name}")
                    # Init QoS tracker for new node
                    if node_name != "Pending" and node_name not in self._qos:
                        self._qos[node_name] = _NodeQoS()
                        self._last_ping[node_name] = 0.0
                        logger.info(f"QoS tracker created for {node_name} ({ip})")
                    # Schedule ping for latency measurement
                    if node_name != "Pending":
                        now = time.time()
                        if now - self._last_ping.get(node_name, 0) > self._ping_interval:
                            self._last_ping[node_name] = now
                            t = threading.Thread(
                                target=self._qos[node_name].update_latency,
                                args=(ip,), daemon=True
                            )
                            t.start()

                if node_name == "Pending":
                    continue # Ignore garbled lines before identification

                # Parse both DATA and DUMMY payloads identically for AI/Storage
                m = None
                if line.startswith("DATA:"):
                    m = _DATA_RE.match(line)
                elif line.startswith("DUMMY:"):
                    m = _DUMMY_RE.match(line)
                    
                if m:
                    parsed_results[node_name] = {
                        "pH": int(m.group(1)) / 1000.0,
                        "T": int(m.group(2)) / 100.0,
                        "risk": int(m.group(3)),
                        "latency_ms": 0.0,
                        "jitter_ms": 0.0,
                        "bandwidth_mbps": 0.0
                    }

        return parsed_results

    # ── QoS Access ───────────────────────────────────────────────────────────── #

    def get_node_qos(self, node_id: str) -> dict:
        """Return measured QoS for a node. Falls back to zeros if not yet measured."""
        if node_id in self._qos:
            return self._qos[node_id].to_dict()
        return {"latency_ms": 0.0, "jitter_ms": 0.0, "bandwidth_mbps": 0.0}

    def write_qos_stats(self, stats_file: str) -> None:
        """
        Merge per-node QoS into callbox_stats.json (creates file if missing).
        Uses atomic rename so the JSON is never partially written.
        """
        try:
            existing = {}
            if os.path.exists(stats_file):
                try:
                    with open(stats_file, "r") as f:
                        existing = json.load(f)
                except Exception:
                    existing = {}

            nodes_data = {nid: qos.to_dict() for nid, qos in self._qos.items()}
            existing["nodes"] = nodes_data
            existing.setdefault("ipsec_status", "DOWN")
            if len(self.clients) > 0:
                existing["ipsec_status"] = "ESTABLISHED"
            existing["connected_picos"] = len(self.clients)

            dir_ = os.path.dirname(os.path.abspath(stats_file))
            os.makedirs(dir_, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=dir_, suffix=".tmp")
            try:
                with os.fdopen(fd, "w") as f:
                    json.dump(existing, f, indent=2)
                os.replace(tmp, stats_file)
            except Exception:
                try:
                    os.unlink(tmp)
                except Exception:
                    pass
                raise
        except Exception as e:
            logger.warning(f"write_qos_stats failed: {e}")

    # ── Send Q-table ─────────────────────────────────────────────────────── #

    def send_qtable(self, qtable_string: str) -> bool:
        """
        Broadcasts Q-table to ALL connected Picos (Main and Dummys) 
        to ensure network bandwidth load is measured accurately.
        Only waits for ACK from the Main Client.
        """
        if not self.clients:
            logger.warning("No clients connected — cannot send Q-table.")
            return False

        msg = (qtable_string + "\n").encode("utf-8")
        
        # Broadcast to all nodes
        for sock in list(self.clients.keys()):
            try:
                sock.sendall(msg)
            except OSError:
                pass
                
        logger.info(f"Q-table broadcasted to {len(self.clients)} Node(s) ({len(msg)} bytes)")

        # Find the main Pico_1_Main socket to wait for ACK
        main_sock = None
        for sock, name in self.node_ids.items():
            if name == "Pico_1_Main":
                main_sock = sock
                break

        if main_sock is None:
            return True  # No main client yet, assume success for dummies

        # Wait for ACK from Pico_1_Main
        start_time = time.time()
        while time.time() - start_time < ACK_TIMEOUT:
            try:
                read_sockets, _, _ = select.select([main_sock], [], [], 0.1)
                if read_sockets:
                    data = main_sock.recv(1024).decode("utf-8", errors="ignore")
                    if not data:
                        return False
                    self.clients[main_sock] += data

                    while "\n" in self.clients[main_sock]:
                        line, self.clients[main_sock] = self.clients[main_sock].split("\n", 1)
                        line = line.strip()

                        if line.startswith("ACK:"):
                            _pico_log.debug(line)
                            if "QTABLE_LOADED" in line:
                                return True
                            elif "QTABLE_ERROR" in line:
                                logger.error("Main Pico reported Q-table error")
                                return False
            except (OSError, ValueError):
                return False

        logger.warning(f"Q-table ACK timeout after {ACK_TIMEOUT}s")
        return False

