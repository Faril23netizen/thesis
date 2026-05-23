"""
WiFi Bridge — bidirectional communication RPi4/5 <-> Pico WH
=============================================================
N3IWF Local Edge Service via TCP Sockets.

RPi5 acts as the TCP Server, waiting for the Pico WH to connect.
Receive : "DATA:ph_x1000,temp_x100,risk\\n"
Send    : "QTABLE:[[...9x4 floats...]]\\n"
Receive : "ACK:QTABLE_LOADED\\n"

Other lines from Pico ("> ...", "# ...") are logged then ignored.
"""

import os
import re
import time
import socket
import logging

logger = logging.getLogger(__name__)

# Dedicated logger for raw Pico monitor lines ("> ..." and "# ...")
_pico_log = logging.getLogger("pico_monitor")
_pico_log.setLevel(logging.DEBUG)
_pico_log.propagate = False  # don't mix into main aquaculture log

def _setup_pico_monitor_log(log_dir: str) -> None:
    """Call once at startup to wire up the pico_monitor file handler."""
    if _pico_log.handlers:
        return  # already configured
    os.makedirs(log_dir, exist_ok=True)
    fh = logging.FileHandler(os.path.join(log_dir, "pico_monitor.log"))
    fh.setFormatter(logging.Formatter(
        "[%(asctime)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    ))
    _pico_log.addHandler(fh)

DEFAULT_PORT = 5000
ACK_TIMEOUT  = 10      # seconds to wait for ACK after sending Q-table
RECONNECT_DELAY = 2    # seconds between reconnect attempts

# Regex for DATA: lines
_DATA_RE = re.compile(r"^DATA:(-?\d+),(-?\d+),([0-3])$")

class WiFiBridge:
    """WiFi communication bridge (TCP Server) for N3IWF."""

    def __init__(self, host: str = "0.0.0.0", port: int = DEFAULT_PORT):
        self.host = host
        self.port = port
        self.server_socket: socket.socket | None = None
        self.client_socket: socket.socket | None = None
        self.client_addr = None
        self._buffer = ""

    # ── Connection ───────────────────────────────────────────────────────── #

    def connect(self) -> bool:
        """
        Start TCP Server and wait for Pico to connect.
        Blocks until connection is established.
        Returns True on success.
        """
        if self.server_socket is None:
            try:
                self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self.server_socket.bind((self.host, self.port))
                self.server_socket.listen(1)
                logger.info(f"N3IWF WiFi Bridge listening on {self.host}:{self.port}")
            except OSError as e:
                logger.error(f"Failed to bind WiFi server: {e}")
                return False

        logger.info("Waiting for Pico WH to connect over Wi-Fi...")
        try:
            # Setting a timeout so it doesn't block forever if we want to interrupt
            self.server_socket.settimeout(5.0)
            while True:
                try:
                    self.client_socket, self.client_addr = self.server_socket.accept()
                    self.client_socket.settimeout(1.0) # Short timeout for reading
                    logger.info(f"Connected to Pico WH at {self.client_addr}")
                    self._buffer = ""
                    return True
                except socket.timeout:
                    # Just loop and wait again, allows Ctrl+C
                    continue
        except KeyboardInterrupt:
            logger.info("Connection wait interrupted by user.")
            return False
        except OSError as e:
            logger.error(f"Error accepting connection: {e}")
            return False

    def disconnect(self) -> None:
        """Close the client connection."""
        if self.client_socket:
            try:
                self.client_socket.close()
            except OSError:
                pass
        self.client_socket = None
        self.client_addr = None
        logger.info("WiFi client connection closed.")

    def is_connected(self) -> bool:
        """Check whether the client is currently connected."""
        return self.client_socket is not None

    def reconnect(self) -> bool:
        """
        Attempt to wait for a new connection after a drop.
        Returns True on success.
        """
        logger.info("Attempting to wait for Pico reconnect...")
        self.disconnect()
        time.sleep(RECONNECT_DELAY)
        return self.connect()

    def _readline(self) -> str | None:
        """Helper to read a complete newline-terminated string from the socket."""
        if not self.is_connected():
            return None
            
        while "\n" not in self._buffer:
            try:
                data = self.client_socket.recv(1024).decode("utf-8", errors="ignore")
                if not data:
                    # Client closed connection
                    raise OSError("Connection closed by peer")
                self._buffer += data
            except socket.timeout:
                return None  # No data right now
            except OSError as e:
                logger.warning(f"WiFi read error: {e}")
                self.disconnect()
                return None

        # Extract the first line and keep the rest in the buffer
        line, self._buffer = self._buffer.split("\n", 1)
        return line.strip()

    # ── Read data ────────────────────────────────────────────────────────── #

    def read_data_line(self) -> dict | None:
        """
        Read one line from Wi-Fi.

        If it starts with "DATA:" -> parse and return:
          {"pH": float, "T": float, "risk": int, "latency_ms": float}

        Other lines (monitor/comment/ACK) -> logged then return None.
        If connection drops -> attempt automatic reconnect.
        """
        if not self.is_connected():
            logger.warning("WiFi disconnected, waiting for Pico to reconnect...")
            if not self.reconnect():
                return None

        line = self._readline()
        if not line:
            return None

        # Monitor/comment lines from Pico -> dedicated pico_monitor.log
        if line.startswith(">") or line.startswith("#"):
            _pico_log.debug(line)
            return None

        # ACK lines -> both main log and pico_monitor.log
        if line.startswith("ACK:"):
            logger.info(f"[pico] {line}")
            _pico_log.debug(line)
            return None

        # Parse DATA: line
        m = _DATA_RE.match(line)
        if not m:
            logger.debug(f"[pico] unknown line: {line}")
            return None

        ph_x1000  = int(m.group(1))
        temp_x100 = int(m.group(2))
        risk      = int(m.group(3))

        return {
            "pH":         ph_x1000  / 1000.0,
            "T":          temp_x100 / 100.0,
            "risk":       risk,
            "latency_ms": 0.0,  # Can be calculated if needed
        }

    # ── Send Q-table ─────────────────────────────────────────────────────── #

    def send_qtable(self, qtable_string: str) -> bool:
        """
        Send Q-table to Pico.
        Waits for "ACK:QTABLE_LOADED\\n" up to ACK_TIMEOUT seconds.
        Returns True if ACK received, False on timeout or error.
        """
        if not self.is_connected():
            logger.warning("Not connected — cannot send Q-table.")
            return False

        # Ensure newline at the end
        if not qtable_string.endswith("\n"):
            qtable_string += "\n"

        try:
            self.client_socket.sendall(qtable_string.encode("utf-8"))
            logger.info(f"Q-table sent via WiFi ({len(qtable_string)} bytes), "
                        f"waiting for ACK (max {ACK_TIMEOUT}s)...")
        except OSError as e:
            logger.warning(f"Failed to send Q-table: {e}")
            self.disconnect()
            return False

        # Wait for ACK
        deadline = time.time() + ACK_TIMEOUT
        while time.time() < deadline:
            line = self._readline()
            if line is None:
                continue

            if line == "ACK:QTABLE_LOADED":
                logger.info("ACK received — Q-table loaded by Pico.")
                return True

            if line == "ACK:QTABLE_ERROR":
                logger.error("ACK error — Pico failed to parse Q-table.")
                return False

            # Other lines received while waiting for ACK
            if line:
                logger.debug(f"[pico waiting ACK] {line}")

        logger.warning("Timeout waiting for ACK from Pico.")
        return False
