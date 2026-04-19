"""
Main FQL — Raspberry Pi 4
==========================
Jalankan otomatis via systemd. Alur:
  FASE A → Tunggu koneksi Pico
  FASE B → FQL belajar dari data Rule-Based
  FASE C → FQL konvergen → kirim Q-table ke Pico
  FASE D → Buffer DQN cukup → siap DQN training
  FASE E → Monitor terus

Jalankan manual:
  python3 main_fql.py

Install sebagai service:
  sudo cp aquaculture.service /etc/systemd/system/
  sudo systemctl enable aquaculture
  sudo systemctl start aquaculture
"""

import json
import logging
import os
import signal
import sys
import time

from fql_agent import FQLAgent
from serial_bridge import SerialBridge

# ── Konfigurasi path ─────────────────────────────────────────────────────── #
BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
QTABLE_FILE    = os.path.join(BASE_DIR, "qtable.json")
BUFFER_FILE    = os.path.join(BASE_DIR, "dqn_buffer.json")
LOG_DIR        = os.path.join(BASE_DIR, "logs")
LOG_FILE       = os.path.join(LOG_DIR, "fql.log")
LOG_ERROR_FILE = os.path.join(LOG_DIR, "fql_error.log")

# ── Konstanta ────────────────────────────────────────────────────────────── #
DQN_BUFFER_READY    = 10_000   # jumlah transisi sebelum DQN siap
DQN_BUFFER_MAX      = 50_000   # batas maksimal buffer (FIFO)
BUFFER_AUTOSAVE     = 500      # simpan buffer setiap N transisi
FQL_RETRY_INTERVAL  = 30       # detik antar retry kirim Q-table
LOG_INTERVAL        = 10       # log detail setiap N step
SUMMARY_INTERVAL    = 100      # log ringkasan setiap N step


# ══════════════════════════════════════════════════════════════════════════ #
#  Setup logging
# ══════════════════════════════════════════════════════════════════════════ #

def setup_logging() -> logging.Logger:
    os.makedirs(LOG_DIR, exist_ok=True)

    fmt = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    logger = logging.getLogger("aquaculture")
    logger.setLevel(logging.DEBUG)

    # Handler ke console
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # Handler ke file fql.log (INFO ke atas)
    fh = logging.FileHandler(LOG_FILE)
    fh.setLevel(logging.INFO)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # Handler ke fql_error.log (WARNING ke atas)
    eh = logging.FileHandler(LOG_ERROR_FILE)
    eh.setLevel(logging.WARNING)
    eh.setFormatter(fmt)
    logger.addHandler(eh)

    return logger


# ══════════════════════════════════════════════════════════════════════════ #
#  Buffer DQN helpers
# ══════════════════════════════════════════════════════════════════════════ #

def load_buffer(path: str) -> list:
    """Load buffer DQN dari file JSON. Return list kosong kalau gagal."""
    try:
        with open(path) as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return []


def save_buffer(buffer: list, path: str) -> None:
    """Simpan buffer DQN ke file JSON."""
    try:
        with open(path, "w") as f:
            json.dump(buffer, f)
    except OSError as e:
        logger.warning(f"Gagal simpan buffer DQN: {e}")


def append_transition(buffer: list, s, a, r, s_next) -> None:
    """
    Tambah satu transisi ke buffer.
    Kalau melebihi DQN_BUFFER_MAX, buang elemen terlama (FIFO).
    """
    buffer.append({
        "s":      s,
        "a":      a,
        "r":      round(r, 5),
        "s_next": s_next,
    })
    if len(buffer) > DQN_BUFFER_MAX:
        buffer.pop(0)


# ══════════════════════════════════════════════════════════════════════════ #
#  Graceful shutdown
# ══════════════════════════════════════════════════════════════════════════ #

_shutdown = False

def _handle_signal(sig, frame):
    global _shutdown
    _shutdown = True

signal.signal(signal.SIGINT,  _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


# ══════════════════════════════════════════════════════════════════════════ #
#  Main
# ══════════════════════════════════════════════════════════════════════════ #

logger = setup_logging()


def main():
    global _shutdown

    logger.info("=" * 60)
    logger.info("Aquaculture FQL Controller — Raspberry Pi 4")
    logger.info("=" * 60)

    # ── Setup objek utama ────────────────────────────────────────────────── #
    fql    = FQLAgent()
    bridge = SerialBridge()
    buffer_dqn: list = []

    # Flag untuk log DQN buffer ready hanya sekali
    dqn_ready_logged = False

    # Waktu terakhir retry kirim Q-table
    last_qtable_retry = 0.0

    # ── Load state sebelumnya kalau ada ─────────────────────────────────── #
    if os.path.exists(QTABLE_FILE):
        if fql.load_qtable(QTABLE_FILE):
            logger.info(f"Q-table dimuat dari {QTABLE_FILE} "
                        f"(step={fql.total_steps}, ε={fql.epsilon:.3f})")
        else:
            logger.warning("Q-table file rusak, mulai dari awal.")

    if os.path.exists(BUFFER_FILE):
        buffer_dqn = load_buffer(BUFFER_FILE)
        if buffer_dqn:
            logger.info(f"Buffer DQN dimuat: {len(buffer_dqn)} transisi")

    # ── FASE A: Tunggu koneksi Pico ──────────────────────────────────────── #
    logger.info("FASE A — Menunggu koneksi Pico WH...")
    while not _shutdown:
        if bridge.connect():
            logger.info("Pico WH terhubung!")
            break
        logger.info(f"Pico belum terdeteksi, coba lagi {RECONNECT_DELAY}s...")
        time.sleep(2)

    if _shutdown:
        _cleanup(fql, buffer_dqn)
        return

    # ── Loop utama ───────────────────────────────────────────────────────── #
    logger.info("FASE B — FQL mulai belajar dari data Rule-Based...")

    prev_data: dict | None = None

    while not _shutdown:
        # ── Terima data dari Pico ────────────────────────────────────────── #
        data = bridge.read_data_line()
        if data is None:
            continue

        pH     = data["pH"]
        T      = data["T"]
        action = data["action"]

        # ── FASE B: Update FQL dari transisi (s_prev → s_now) ────────────── #
        if prev_data is not None:
            pH_prev     = prev_data["pH"]
            T_prev      = prev_data["T"]
            action_prev = prev_data["action"]
            prev_action_before = prev_data.get("prev_action")

            # Hitung reward berdasarkan state sebelumnya + aksi + state sekarang
            reward = fql.compute_reward(
                pH_prev, T_prev, action_prev,
                pH, T,
                prev_action_before
            )

            # Update Q-table
            fql.update(pH_prev, T_prev, action_prev, reward, pH, T)

            # Simpan transisi ke buffer DQN
            append_transition(buffer_dqn,
                              s      = [pH_prev, T_prev],
                              a      = action_prev,
                              r      = reward,
                              s_next = [pH, T])

            # Auto-save buffer setiap BUFFER_AUTOSAVE transisi
            if len(buffer_dqn) % BUFFER_AUTOSAVE == 0 and len(buffer_dqn) > 0:
                save_buffer(buffer_dqn, BUFFER_FILE)
                logger.debug(f"Buffer DQN auto-saved: {len(buffer_dqn)} transisi")

            # ── FASE D: Cek buffer DQN cukup ─────────────────────────────── #
            if len(buffer_dqn) >= DQN_BUFFER_READY and not dqn_ready_logged:
                logger.info("=" * 60)
                logger.info(f"=== DQN BUFFER READY: {len(buffer_dqn)} transisi ===")
                logger.info("=== Siap untuk DQN training ===")
                logger.info("=" * 60)
                dqn_ready_logged = True

            # ── FASE C: Cek konvergensi FQL ──────────────────────────────── #
            if fql.check_convergence() and not fql.converged_sent:
                stats = fql.get_stats()
                logger.info("=" * 60)
                logger.info(f"=== FQL CONVERGED === "
                            f"Step: {stats['total_steps']} | "
                            f"Avg Reward: {stats['avg_reward_prev_100']:.4f} ===")
                logger.info("=" * 60)

                fql.save_qtable(QTABLE_FILE)
                logger.info(f"Q-table disimpan ke {QTABLE_FILE}")

                qtable_str = fql.get_qtable_string()
                if bridge.send_qtable(qtable_str):
                    logger.info("Q-table berhasil dikirim ke Pico WH")
                    fql.converged_sent = True
                else:
                    logger.warning(
                        f"GAGAL kirim Q-table — "
                        f"retry dalam {FQL_RETRY_INTERVAL}s"
                    )
                    last_qtable_retry = time.time()

            # Retry kirim Q-table kalau sebelumnya gagal
            elif (fql.converged and
                  not fql.converged_sent and
                  time.time() - last_qtable_retry > FQL_RETRY_INTERVAL):
                logger.info("Retry kirim Q-table ke Pico...")
                qtable_str = fql.get_qtable_string()
                if bridge.send_qtable(qtable_str):
                    logger.info("Q-table berhasil dikirim ke Pico WH (retry)")
                    fql.converged_sent = True
                else:
                    last_qtable_retry = time.time()

            # ── Logging berkala ───────────────────────────────────────────── #
            if fql.total_steps % LOG_INTERVAL == 0:
                stats = fql.get_stats()
                logger.info(
                    f"[{stats['total_steps']:5d}] "
                    f"pH:{pH:.3f} T:{T:.1f}°C "
                    f"Aksi:{action} "
                    f"ε:{stats['epsilon']:.3f} "
                    f"AvgR:{stats['avg_reward_100']:+.3f} "
                    f"Buffer:{len(buffer_dqn)}"
                )

            if fql.total_steps % SUMMARY_INTERVAL == 0:
                stats = fql.get_stats()
                logger.info("-" * 60)
                logger.info(
                    f"Step {stats['total_steps']} | "
                    f"Avg Reward: {stats['avg_reward_prev_100']:+.4f} | "
                    f"Delta: {abs(stats['avg_reward_prev_100'] - stats['avg_reward_prev2']):.4f} | "
                    f"Converged: {stats['converged']} | "
                    f"Buffer DQN: {len(buffer_dqn)}"
                )
                logger.info("-" * 60)

        # Simpan data saat ini untuk jadi prev pada iterasi berikutnya
        prev_data = {
            "pH":          pH,
            "T":           T,
            "action":      action,
            "prev_action": prev_data["action"] if prev_data else None,
        }

    # ── Cleanup saat shutdown ─────────────────────────────────────────────── #
    _cleanup(fql, buffer_dqn)
    bridge.disconnect()


def _cleanup(fql: FQLAgent, buffer_dqn: list) -> None:
    """Simpan semua state sebelum keluar."""
    logger.info("Sistem dihentikan — menyimpan data...")
    fql.save_qtable(QTABLE_FILE)
    save_buffer(buffer_dqn, BUFFER_FILE)
    logger.info(f"Q-table disimpan: {QTABLE_FILE}")
    logger.info(f"Buffer DQN disimpan: {BUFFER_FILE} ({len(buffer_dqn)} transisi)")
    logger.info("Sistem dihentikan — data disimpan.")


if __name__ == "__main__":
    main()
