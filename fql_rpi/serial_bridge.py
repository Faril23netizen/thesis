"""
Serial Bridge — komunikasi dua arah RPi4 ↔ Pico WH
====================================================
Terima : "DATA:ph_x1000,temp_x100,action\\n"
Kirim  : "QTABLE:[[...9×4 floats...]]\\n"
Terima : "ACK:QTABLE_LOADED\\n"

Baris lain dari Pico ("> ...", "# ...") di-log lalu diabaikan.
"""

import re
import time
import glob
import logging
import serial
import serial.tools.list_ports

logger = logging.getLogger(__name__)

BAUD_RATE    = 115200
ACK_TIMEOUT  = 10      # detik tunggu ACK setelah kirim Q-table
RECONNECT_DELAY = 2    # detik antar percobaan reconnect

# Regex untuk baris DATA:
_DATA_RE = re.compile(r"^DATA:(-?\d+),(-?\d+),([0-3])$")


class SerialBridge:
    """Jembatan komunikasi serial antara RPi4 dan Pico WH."""

    def __init__(self, baudrate: int = BAUD_RATE, timeout: int = 3):
        self.baudrate  = baudrate
        self.timeout   = timeout
        self._ser: serial.Serial | None = None
        self._port: str | None = None

    # ── Deteksi port ─────────────────────────────────────────────────────── #

    def auto_detect_port(self) -> str | None:
        """
        Cari port Pico secara otomatis.
        Scan /dev/ttyACM* dan /dev/ttyUSB*, cari VID Raspberry Pi (0x2E8A).
        """
        # Prioritas 1: cari berdasarkan VID
        for p in serial.tools.list_ports.comports():
            vid = f"{p.vid:04X}" if p.vid else ""
            if "2E8A" in vid:
                logger.info(f"Port Pico ditemukan via VID: {p.device}")
                return p.device

        # Prioritas 2: cari berdasarkan nama deskripsi
        for p in serial.tools.list_ports.comports():
            desc = (p.description or "").lower()
            if "pico" in desc or "micropython" in desc or "cdc" in desc:
                logger.info(f"Port Pico ditemukan via deskripsi: {p.device}")
                return p.device

        # Prioritas 3: ambil /dev/ttyACM0 atau /dev/ttyACM1 kalau ada
        for candidate in ["/dev/ttyACM0", "/dev/ttyACM1", "/dev/ttyUSB0"]:
            ports = glob.glob(candidate)
            if ports:
                logger.info(f"Port fallback ditemukan: {ports[0]}")
                return ports[0]

        return None

    # ── Koneksi ──────────────────────────────────────────────────────────── #

    def connect(self) -> bool:
        """
        Coba koneksi ke Pico.
        Return True kalau berhasil, False kalau gagal.
        """
        port = self.auto_detect_port()
        if port is None:
            logger.warning("Tidak ada port Pico ditemukan.")
            return False
        try:
            self._ser  = serial.Serial(port, self.baudrate, timeout=self.timeout)
            self._port = port
            logger.info(f"Terhubung ke {port} @ {self.baudrate} baud")
            return True
        except serial.SerialException as e:
            logger.warning(f"Gagal koneksi ke {port}: {e}")
            self._ser = None
            return False

    def disconnect(self) -> None:
        """Tutup koneksi serial."""
        if self._ser and self._ser.is_open:
            self._ser.close()
        self._ser = None
        logger.info("Koneksi serial ditutup.")

    def is_connected(self) -> bool:
        """Cek apakah serial masih terbuka."""
        return self._ser is not None and self._ser.is_open

    def reconnect(self) -> bool:
        """
        Coba koneksi ulang kalau putus.
        Return True kalau berhasil.
        """
        logger.info("Mencoba reconnect ke Pico...")
        self.disconnect()
        time.sleep(RECONNECT_DELAY)
        return self.connect()

    # ── Baca data ────────────────────────────────────────────────────────── #

    def read_data_line(self) -> dict | None:
        """
        Baca satu baris dari serial.

        Kalau dimulai "DATA:" → parse dan return:
          {"pH": float, "T": float, "action": int}

        Baris lain (monitor/comment/ACK) → di-log lalu return None.
        Kalau koneksi putus → coba reconnect otomatis.
        """
        if not self.is_connected():
            logger.warning("Serial putus, mencoba reconnect...")
            if not self.reconnect():
                return None

        try:
            raw  = self._ser.readline()
            line = raw.decode("utf-8", errors="ignore").strip()
        except (serial.SerialException, OSError) as e:
            logger.warning(f"Error baca serial: {e}")
            self._ser = None
            return None

        if not line:
            return None

        # Tampilkan baris monitor/comment dari Pico
        if line.startswith(">") or line.startswith("#"):
            logger.debug(f"[pico] {line}")
            return None

        # Tangani ACK (untuk logging — ACK yang ditunggu di send_qtable)
        if line.startswith("ACK:"):
            logger.info(f"[pico] {line}")
            return None

        # Parse baris DATA:
        m = _DATA_RE.match(line)
        if not m:
            logger.debug(f"[pico] baris tidak dikenal: {line}")
            return None

        ph_x1000  = int(m.group(1))
        temp_x100 = int(m.group(2))
        action    = int(m.group(3))

        return {
            "pH":    ph_x1000  / 1000.0,
            "T":     temp_x100 / 100.0,
            "action": action,
        }

    # ── Kirim Q-table ────────────────────────────────────────────────────── #

    def send_qtable(self, qtable_string: str) -> bool:
        """
        Kirim Q-table ke Pico.
        Tunggu "ACK:QTABLE_LOADED\\n" maksimal ACK_TIMEOUT detik.
        Return True kalau ACK diterima, False kalau timeout/error.
        """
        if not self.is_connected():
            logger.warning("Tidak terhubung — tidak bisa kirim Q-table.")
            return False

        try:
            self._ser.write(qtable_string.encode("utf-8"))
            self._ser.flush()
            logger.info(f"Q-table dikirim ({len(qtable_string)} bytes), "
                        f"menunggu ACK maksimal {ACK_TIMEOUT}s...")
        except (serial.SerialException, OSError) as e:
            logger.warning(f"Gagal kirim Q-table: {e}")
            return False

        # Tunggu ACK
        deadline = time.time() + ACK_TIMEOUT
        while time.time() < deadline:
            try:
                raw  = self._ser.readline()
                line = raw.decode("utf-8", errors="ignore").strip()
            except (serial.SerialException, OSError):
                break

            if line == "ACK:QTABLE_LOADED":
                logger.info("ACK diterima — Q-table berhasil dimuat Pico.")
                return True

            if line == "ACK:QTABLE_ERROR":
                logger.error("ACK error — Pico gagal parse Q-table.")
                return False

            # Baris lain selama nunggu ACK
            if line:
                logger.debug(f"[pico saat tunggu ACK] {line}")

        logger.warning("Timeout menunggu ACK dari Pico.")
        return False
