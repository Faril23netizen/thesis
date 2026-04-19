"""
Serial Bridge — bidirectional communication RPi4 <-> Pico WH
=============================================================
Receive : "DATA:ph_x1000,temp_x100,action\\n"
Send    : "QTABLE:[[...9x4 floats...]]\\n"
Receive : "ACK:QTABLE_LOADED\\n"

Other lines from Pico ("> ...", "# ...") are logged then ignored.
"""

import re
import time
import glob
import logging
import serial
import serial.tools.list_ports

logger = logging.getLogger(__name__)

BAUD_RATE    = 115200
ACK_TIMEOUT  = 10      # seconds to wait for ACK after sending Q-table
RECONNECT_DELAY = 2    # seconds between reconnect attempts

# Regex for DATA: lines
_DATA_RE = re.compile(r"^DATA:(-?\d+),(-?\d+),([0-3])$")


class SerialBridge:
    """Serial communication bridge between RPi4 and Pico WH."""

    def __init__(self, baudrate: int = BAUD_RATE, timeout: int = 3):
        self.baudrate  = baudrate
        self.timeout   = timeout
        self._ser: serial.Serial | None = None
        self._port: str | None = None

    # ── Port detection ───────────────────────────────────────────────────── #

    def auto_detect_port(self) -> str | None:
        """
        Auto-detect Pico port.
        Scans /dev/ttyACM* and /dev/ttyUSB*, matches Raspberry Pi VID (0x2E8A).
        """
        # Priority 1: match by VID
        for p in serial.tools.list_ports.comports():
            vid = f"{p.vid:04X}" if p.vid else ""
            if "2E8A" in vid:
                logger.info(f"Pico port found by VID: {p.device}")
                return p.device

        # Priority 2: match by description string
        for p in serial.tools.list_ports.comports():
            desc = (p.description or "").lower()
            if "pico" in desc or "micropython" in desc or "cdc" in desc:
                logger.info(f"Pico port found by description: {p.device}")
                return p.device

        # Priority 3: fallback to /dev/ttyACM0, /dev/ttyACM1, /dev/ttyUSB0
        for candidate in ["/dev/ttyACM0", "/dev/ttyACM1", "/dev/ttyUSB0"]:
            ports = glob.glob(candidate)
            if ports:
                logger.info(f"Fallback port found: {ports[0]}")
                return ports[0]

        return None

    # ── Connection ───────────────────────────────────────────────────────── #

    def connect(self) -> bool:
        """
        Attempt connection to Pico.
        Returns True on success, False on failure.
        """
        port = self.auto_detect_port()
        if port is None:
            logger.warning("No Pico port found.")
            return False
        try:
            self._ser  = serial.Serial(port, self.baudrate, timeout=self.timeout)
            self._port = port
            logger.info(f"Connected to {port} @ {self.baudrate} baud")
            return True
        except serial.SerialException as e:
            logger.warning(f"Failed to connect to {port}: {e}")
            self._ser = None
            return False

    def disconnect(self) -> None:
        """Close the serial connection."""
        if self._ser and self._ser.is_open:
            self._ser.close()
        self._ser = None
        logger.info("Serial connection closed.")

    def is_connected(self) -> bool:
        """Check whether the serial port is open."""
        return self._ser is not None and self._ser.is_open

    def reconnect(self) -> bool:
        """
        Attempt to reconnect after a drop.
        Returns True on success.
        """
        logger.info("Attempting reconnect to Pico...")
        self.disconnect()
        time.sleep(RECONNECT_DELAY)
        return self.connect()

    # ── Read data ────────────────────────────────────────────────────────── #

    def read_data_line(self) -> dict | None:
        """
        Read one line from serial.

        If it starts with "DATA:" -> parse and return:
          {"pH": float, "T": float, "action": int}

        Other lines (monitor/comment/ACK) -> logged then return None.
        If connection drops -> attempt automatic reconnect.
        """
        if not self.is_connected():
            logger.warning("Serial disconnected, attempting reconnect...")
            if not self.reconnect():
                return None

        try:
            raw  = self._ser.readline()
            line = raw.decode("utf-8", errors="ignore").strip()
        except (serial.SerialException, OSError) as e:
            logger.warning(f"Serial read error: {e}")
            self._ser = None
            return None

        if not line:
            return None

        # Log monitor/comment lines from Pico
        if line.startswith(">") or line.startswith("#"):
            logger.debug(f"[pico] {line}")
            return None

        # Handle ACK lines (logging only — blocking ACK is handled in send_qtable)
        if line.startswith("ACK:"):
            logger.info(f"[pico] {line}")
            return None

        # Parse DATA: line
        m = _DATA_RE.match(line)
        if not m:
            logger.debug(f"[pico] unknown line: {line}")
            return None

        ph_x1000  = int(m.group(1))
        temp_x100 = int(m.group(2))
        action    = int(m.group(3))

        return {
            "pH":    ph_x1000  / 1000.0,
            "T":     temp_x100 / 100.0,
            "action": action,
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

        try:
            self._ser.write(qtable_string.encode("utf-8"))
            self._ser.flush()
            logger.info(f"Q-table sent ({len(qtable_string)} bytes), "
                        f"waiting for ACK (max {ACK_TIMEOUT}s)...")
        except (serial.SerialException, OSError) as e:
            logger.warning(f"Failed to send Q-table: {e}")
            return False

        # Wait for ACK
        deadline = time.time() + ACK_TIMEOUT
        while time.time() < deadline:
            try:
                raw  = self._ser.readline()
                line = raw.decode("utf-8", errors="ignore").strip()
            except (serial.SerialException, OSError):
                break

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
