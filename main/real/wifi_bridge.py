import os
import re
import time
import socket
import select
import logging

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
                return False

        logger.info("Waiting for Pico WH to connect over Wi-Fi...")
        try:
            # Block until the first client connects
            while True:
                read_sockets, _, _ = select.select([self.server_socket], [], [], 1.0)
                if read_sockets:
                    client, addr = self.server_socket.accept()
                    client.setblocking(False)
                    self.clients[client] = ""
                    self.node_ids[client] = "Pending"
                    logger.info(f"Connected to {addr[0]}, waiting for payload to identify...")
                    return True
        except KeyboardInterrupt:
            logger.info("Connection wait interrupted by user.")
            return False

    def disconnect(self) -> None:
        """Close all client connections and server socket."""
        for client in list(self.clients.keys()):
            client.close()
        self.clients.clear()
        self.node_ids.clear()
        self.ip_to_name.clear()
        self.dummy_counter = 2
        
        if self.server_socket:
            self.server_socket.close()
            self.server_socket = None
        logger.info("WiFi bridge disconnected.")

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
                    data = sock.recv(1024).decode("utf-8", errors="ignore")
                    if not data:
                        # Client disconnected
                        addr = sock.getpeername()
                        node_name = self.node_ids.get(sock, "Pending")
                        logger.warning(f"Client {node_name} ({addr[0]}) disconnected.")
                        del self.clients[sock]
                        del self.node_ids[sock]
                        sock.close()
                        continue
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
                    if line.startswith("DATA:"):
                        node_name = "Pico_1_Main"
                        self.ip_to_name[ip] = node_name
                        self.node_ids[sock] = node_name
                        logger.info(f"Identified {ip} as {node_name}")
                    elif line.startswith("DUMMY:"):
                        if ip in self.ip_to_name:
                            node_name = self.ip_to_name[ip]
                        else:
                            node_name = f"Pico_{self.dummy_counter}_Dummy"
                            self.dummy_counter += 1
                            self.ip_to_name[ip] = node_name
                        self.node_ids[sock] = node_name
                        logger.info(f"Identified {ip} as {node_name}")

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

        if not self.main_client:
            return True # If no main client yet, assume success for dummies

        # Wait for ACK from main_client
        start_time = time.time()
        while time.time() - start_time < ACK_TIMEOUT:
            try:
                read_sockets, _, _ = select.select([self.main_client], [], [], 0.1)
                if read_sockets:
                    sock = read_sockets[0]
                    data = sock.recv(1024).decode("utf-8", errors="ignore")
                    if not data:
                        return False
                    self.clients[sock] += data
                    
                    while "\n" in self.clients[sock]:
                        line, self.clients[sock] = self.clients[sock].split("\n", 1)
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

