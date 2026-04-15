#!/usr/bin/env python3
"""
hvlogger.py - Slow HV monitoring logger for Grafana / time-series DB.

Connects to hvserver via ZeroMQ, polls channel telemetry, server health,
and logger self-health at a configurable interval, then writes everything
to a time-series database.

DB write stubs are intentionally left empty.  Fill them in after choosing a DB
(e.g. InfluxDB, TimescaleDB, Prometheus, etc.).

Usage:
    python hvlogger.py [--interval N] [--host HOST] [--daemon] [--pid FILE]
"""

import sys
import os
import time
import signal
import logging
import argparse
import resource
from datetime import datetime, timezone

import hvconfig
from hvclient import HVClient


# ---------------------------------------------------------------------------
# Time-series DB stubs
# ---------------------------------------------------------------------------

def db_connect():
    """
    Establish and return a connection / client object to the time-series DB.
    Called once at startup.

    Return:
        db  -- any object representing the DB session (or None for a dry run)
    """
    # TODO: implement DB connection
    # Example (InfluxDB v2):
    #   from influxdb_client import InfluxDBClient
    #   return InfluxDBClient(url=URL, token=TOKEN, org=ORG)
    logging.warning(
        "[DB] db_connect() not implemented — running in dry-run mode")
    return None


def db_write_channels(db, records: list[dict]):
    """
    Write per-channel telemetry records to the time-series DB.

    Each record dict contains:
        timestamp  (datetime, UTC)
        slot       (int)
        channel    (int)
        vmon       (float)   Volts
        imon       (float)   µA
        status     (int)     raw bitmask
        is_on      (bool)
        is_ramping (bool)
        is_ovc     (bool)
        is_trip    (bool)
    """
    # TODO: implement channel DB write
    pass


def db_write_server_health(db, record: dict):
    """
    Write hvserver health metrics to the time-series DB.

    record dict contains:
        timestamp  (datetime, UTC)
        alive      (bool)   True if server responded
        ping_ms    (float)  round-trip time in milliseconds (NaN if dead)
    """
    # TODO: implement server health DB write
    pass


def db_write_logger_health(db, record: dict):
    """
    Write logger self-health metrics to the time-series DB.

    record dict contains:
        timestamp    (datetime, UTC)
        uptime_s     (float)   seconds since logger started
        cycle_count  (int)     number of completed collection cycles
        error_count  (int)     cumulative collection errors
        mem_rss_mb   (float)   resident memory usage in MB
    """
    # TODO: implement logger self-health DB write
    # Example (InfluxDB):
    #   p = (Point("hv_logger")
    #        .field("uptime_s",    record["uptime_s"])
    #        .field("cycle_count", record["cycle_count"])
    #        .field("error_count", record["error_count"])
    #        .field("mem_rss_mb",  record["mem_rss_mb"])
    #        .time(record["timestamp"]))
    #   write_api.write(bucket=BUCKET, record=p)
    pass


def db_close(db):
    """Close the DB connection / release resources."""
    # TODO: implement DB close
    pass


# ---------------------------------------------------------------------------
# Daemonization
# ---------------------------------------------------------------------------

def daemonize():
    """Standard double-fork daemonization."""
    try:
        if os.fork() > 0:
            sys.exit(0)
    except OSError as e:
        sys.stderr.write(f"Fork #1 failed: {e}\n")
        sys.exit(1)

    os.chdir("/")
    os.setsid()
    os.umask(0)

    try:
        if os.fork() > 0:
            sys.exit(0)
    except OSError as e:
        sys.stderr.write(f"Fork #2 failed: {e}\n")
        sys.exit(1)

    # Redirect stdio to /dev/null
    sys.stdout.flush()
    sys.stderr.flush()
    with open('/dev/null', 'r') as f:
        os.dup2(f.fileno(), sys.stdin.fileno())
    with open('/dev/null', 'a+') as f:
        os.dup2(f.fileno(), sys.stdout.fileno())
        os.dup2(f.fileno(), sys.stderr.fileno())


# ---------------------------------------------------------------------------
# Monitoring helpers
# ---------------------------------------------------------------------------

def ping_server(client: HVClient) -> tuple[bool, float]:
    """
    Send a ping to hvserver and measure round-trip time.

    Returns:
        (alive: bool, ping_ms: float)  ping_ms is float('nan') if dead
    """
    t0 = time.perf_counter()
    alive = client.check_server()
    dt_ms = (time.perf_counter() - t0) * 1000.0
    return alive, (dt_ms if alive else float('nan'))


def get_mem_rss_mb() -> float:
    """Return current process RSS memory in MB."""
    usage = resource.getrusage(resource.RUSAGE_SELF)
    # ru_maxrss is in KB on Linux, bytes on macOS
    if sys.platform == "darwin":
        return usage.ru_maxrss / 1024 / 1024
    return usage.ru_maxrss / 1024


def collect_and_write(client: HVClient, db,
                      start_time: float, cycle_count: int, error_count: int) -> None:
    """
    One monitoring cycle:
      1. Ping the server        → server health record
      2. Poll channel telemetry → per-channel records
      3. Report logger health   → self-health record
    """
    now = datetime.now(timezone.utc)

    # --- 1. Server health ---
    alive, ping_ms = ping_server(client)
    server_record = {
        "timestamp": now,
        "alive":     alive,
        "ping_ms":   ping_ms,
    }
    if alive:
        logging.info(f"Server alive  ping={ping_ms:.1f} ms")
    else:
        logging.warning("Server NOT responding!")
    db_write_server_health(db, server_record)

    # --- 2. Channel telemetry ---
    if alive:
        data = client.poll_data()
        if data:
            channel_records = []
            for ch in data:
                status = ch.get("status", 0)
                record = {
                    "timestamp":  now,
                    "slot":       ch["slot"],
                    "channel":    ch["channel"],
                    "vmon":       ch["vmon"],
                    "imon":       ch["imon"],
                    "status":     status,
                    "is_on":      bool(status & (1 << 0)),
                    "is_ramping": bool(status & ((1 << 1) | (1 << 2))),
                    "is_ovc":     bool(status & (1 << 3)),
                    "is_trip":    bool(status & (1 << 8)),
                }
                channel_records.append(record)
                logging.debug(
                    f"  S{ch['slot']:02d}/C{ch['channel']:02d}  "
                    f"V={ch['vmon']:7.2f} V  I={ch['imon']:7.3f} µA  "
                    f"status={status:#06x}"
                )
            logging.info(f"Collected {len(channel_records)} channel(s).")
            db_write_channels(db, channel_records)
        else:
            logging.warning("No telemetry data received from server.")

    # --- 3. Logger self-health ---
    uptime_s = time.monotonic() - start_time
    mem_mb = get_mem_rss_mb()
    logger_record = {
        "timestamp":   now,
        "uptime_s":    uptime_s,
        "cycle_count": cycle_count,
        "error_count": error_count,
        "mem_rss_mb":  mem_mb,
    }
    logging.info(
        f"Logger health  uptime={uptime_s:.0f}s  "
        f"cycles={cycle_count}  errors={error_count}  mem={mem_mb:.1f} MB"
    )
    db_write_logger_health(db, logger_record)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="CAEN HV Slow-Control Logger for Grafana / time-series DB")
    parser.add_argument("--host",     default="localhost",
                        help="hvserver host (default: localhost)")
    parser.add_argument("--interval", type=float, default=hvconfig.LOGGER_INTERVAL,
                        help=f"Polling interval in seconds (default: {hvconfig.LOGGER_INTERVAL})")
    parser.add_argument("--daemon",   action="store_true",
                        help="Run in background (daemonize)")
    parser.add_argument("--pid",      default=hvconfig.LOGGER_PID_FILE,
                        help=f"PID file path (default: {hvconfig.LOGGER_PID_FILE})")
    parser.add_argument("--log",      default=hvconfig.LOGGER_LOG_FILE,
                        help=f"Log file path (default: {hvconfig.LOGGER_LOG_FILE})")
    parser.add_argument("--debug",    action="store_true",
                        help="Enable debug logging")
    args = parser.parse_args()

    # Resolve file paths to absolute NOW (before daemonize chdir("/"))
    args.log = os.path.abspath(args.log)
    args.pid = os.path.abspath(args.pid)

    # Logging setup
    log_level = logging.DEBUG if args.debug else logging.INFO
    log_handlers = [logging.FileHandler(args.log)]
    if not args.daemon:
        log_handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=log_handlers,
    )

    # Check for stale PID file
    if os.path.exists(args.pid):
        try:
            with open(args.pid) as f:
                old_pid = int(f.read().strip())
            os.kill(old_pid, 0)
            logging.error(
                f"Logger already running with PID {old_pid}. Exiting.")
            sys.exit(1)
        except (OSError, ValueError):
            logging.warning("Stale PID file found. Cleaning up.")
            os.remove(args.pid)

    if args.daemon:
        logging.info("Daemonizing logger...")
        daemonize()

    # Write PID file (after fork so we have the final PID)
    with open(args.pid, 'w') as f:
        f.write(str(os.getpid()))

    logging.info(
        f"HV Logger started  PID={os.getpid()}  "
        f"host={args.host}  interval={args.interval}s"
    )

    # ZeroMQ client
    client = HVClient(
        cmd_url=f"tcp://{args.host}:{hvconfig.CMD_PORT}",
        sub_url=f"tcp://{args.host}:{hvconfig.PUB_PORT}",
    )

    # DB connection
    db = db_connect()

    # Graceful shutdown
    running = True
    start_time = time.monotonic()
    cycle_count = 0
    error_count = 0

    def _stop(sig, frame):
        nonlocal running
        logging.info(f"Caught SIGNAL {sig}. Shutting down.")
        running = False

    signal.signal(signal.SIGINT,  _stop)
    signal.signal(signal.SIGTERM, _stop)

    # Main loop
    try:
        while running:
            try:
                collect_and_write(client, db, start_time,
                                  cycle_count, error_count)
                cycle_count += 1
            except Exception as e:
                error_count += 1
                logging.error(f"Collection error (total={error_count}): {e}")

            # Sleep in short steps to stay responsive to signals
            deadline = time.monotonic() + args.interval
            while running and time.monotonic() < deadline:
                time.sleep(0.5)
    finally:
        logging.info("Closing connections...")
        client.close()
        db_close(db)
        # Remove PID file
        if os.path.exists(args.pid):
            try:
                with open(args.pid) as f:
                    if int(f.read().strip()) == os.getpid():
                        os.remove(args.pid)
            except Exception:
                pass
        logging.info(
            f"HV Logger stopped.  "
            f"cycles={cycle_count}  errors={error_count}  "
            f"uptime={time.monotonic() - start_time:.0f}s"
        )


if __name__ == "__main__":
    main()
