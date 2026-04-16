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
from hvchannel import load_hv_table

try:
    from influxdb_client import InfluxDBClient, Point
    from influxdb_client.client.write_api import SYNCHRONOUS
except ImportError:
    print("influxdb_client not installed. Please run: pip install influxdb-client")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Time-series DB stubs
# ---------------------------------------------------------------------------

def db_connect():
    """
    Establish and return a connection / client object to the time-series DB.
    Called once at startup.
    """
    try:
        client = InfluxDBClient(
            url=hvconfig.INFLUX_URL,
            token=hvconfig.INFLUX_TOKEN,
            org=hvconfig.INFLUX_ORG
        )
        return client
    except Exception as e:
        logging.error(f"[DB] Connection failed: {e}")
        return None

def db_write_channels(db, records: list[dict]):
    if not db: return
    write_api = db.write_api(write_options=SYNCHRONOUS)
    points = []
    for r in records:
        p = (Point("hv_channel")
             .tag("slot", str(r["slot"]))
             .tag("channel", str(r["channel"]))
             .field("vmon", float(r["vmon"]))
             .field("imon", float(r["imon"]))
             .field("status", int(r["status"]))
             .field("is_on", int(r["is_on"]))
             .field("is_ramping", int(r["is_ramping"]))
             .field("is_ovc", int(r["is_ovc"]))
             .field("is_trip", int(r["is_trip"]))
             .time(r["timestamp"]))
        points.append(p)
    try:
        write_api.write(bucket=hvconfig.INFLUX_BUCKET, org=hvconfig.INFLUX_ORG, record=points)
    except Exception as e:
        logging.error(f"[DB] Failed to write channel data: {e}")

def db_write_server_health(db, record: dict):
    if not db: return
    write_api = db.write_api(write_options=SYNCHRONOUS)
    p = (Point("hv_server")
         .field("server_connected", int(record["server_connected"]))
         .field("ping_ms", float(record["ping_ms"]))
         .field("uptime_s", float(record["uptime_s"]))
         .field("channel_count", int(record["channel_count"]))
         .field("error_count", int(record["error_count"]))
         .time(record["timestamp"]))
         
    if record["caen_connected"] is not None:
        p.field("caen_connected", int(record["caen_connected"]))
        
    try:
        write_api.write(bucket=hvconfig.INFLUX_BUCKET, org=hvconfig.INFLUX_ORG, record=p)
    except Exception as e:
        logging.error(f"[DB] Failed to write server health: {e}")

def db_write_logger_health(db, record: dict):
    if not db: return
    write_api = db.write_api(write_options=SYNCHRONOUS)
    p = (Point("hv_logger")
         .field("uptime_s", float(record["uptime_s"]))
         .field("cycle_count", int(record["cycle_count"]))
         .field("error_count", int(record["error_count"]))
         .field("mem_rss_mb", float(record["mem_rss_mb"]))
         .time(record["timestamp"]))
    try:
        write_api.write(bucket=hvconfig.INFLUX_BUCKET, org=hvconfig.INFLUX_ORG, record=p)
    except Exception as e:
        logging.error(f"[DB] Failed to write logger health: {e}")

def db_close(db):
    if db:
        db.close()



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


def collect_and_write(client, db, start_time, cycle_count, error_count, prev_alive, target_channels=None):
    """
    Executes one cycle of HV data collection and writes to DB.

    Returns:
        alive (bool) -- the server_connected state during this cycle
    """
    now = datetime.now(timezone.utc)

    # --- 1. Server health ---
    alive, ping_ms = ping_server(client)

    # Detect and log state transitions
    if alive and not prev_alive:
        logging.info("hvserver reconnected — resuming normal mode.")
    elif not alive and prev_alive:
        logging.warning("hvserver stopped — entering degraded mode.")
        client.latest_data = None   # clear stale telemetry

    server_record = {
        "timestamp":        now,
        "server_connected": False,
        "ping_ms":          ping_ms,
        "caen_connected":   None,
        "uptime_s":         float('nan'),
        "channel_count":    0,
        "error_count":      0,
    }
    if alive:
        server_record["server_connected"] = True
        try:
            srv_health = client.send_command("get_server_health")
            hw_state = srv_health["hw_state"]
            
            caen_connected = (hw_state == "operational")
            server_record["caen_connected"] = caen_connected
            server_record["uptime_s"]       = srv_health["uptime_s"]
            server_record["channel_count"]  = srv_health["channel_count"]
            server_record["error_count"]    = srv_health["error_count"]
            
            status_str = "RUNNING" if caen_connected else "DEGRADED"
            logging.info(
                f"Server {status_str}  "
                f"ping={ping_ms:.1f} ms  caen_connected={caen_connected}  "
                f"uptime={srv_health['uptime_s']:.0f}s  "
                f"channels={srv_health['channel_count']}  "
                f"errors={srv_health['error_count']}"
            )
        except Exception as e:
            logging.warning(f"get_server_health failed: {e}")
            logging.info(f"Server alive  ping={ping_ms:.1f} ms")
    else:
        logging.warning("Server unreachable  [DEGRADED MODE]")
    db_write_server_health(db, server_record)

    # --- 2. Channel telemetry ---
    if alive:
        data = client.poll_data()
        if data:
            channel_records = []
            for ch in data:
                # If target_channels is provided, filter out unmapped channels
                if target_channels is not None:
                    if (ch["slot"], ch["channel"]) not in target_channels:
                        continue

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
        "timestamp":     now,
        "uptime_s":      uptime_s,
        "cycle_count":   cycle_count,
        "error_count":   error_count,
        "mem_rss_mb":    mem_mb,
    }
    log_status = "OK" if alive else "DEGRADED (Server Unreachable)"
    logging.info(
        f"Logger {log_status}  uptime={uptime_s:.0f}s  "
        f"cycles={cycle_count}  errors={error_count}  mem={mem_mb:.1f} MB"
    )

    db_write_logger_health(db, logger_record)

    return alive


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
    parser.add_argument("--table",    default=hvconfig.HV_TABLE,
                        help=f"Path to the channel configuration file (default: {hvconfig.HV_TABLE})")
    parser.add_argument("--debug",    action="store_true",
                        help="Enable debug logging")
    args = parser.parse_args()

    # Resolve file paths to absolute NOW (before daemonize chdir("/"))
    args.log = os.path.abspath(args.log)
    args.pid = os.path.abspath(args.pid)
    args.table = os.path.abspath(args.table)

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
    server_alive = False   # track server reachability across cycles
    target_channels = set()
    last_table_mtime = 0

    try:
        while running:
            # Check if hv.table has been updated (hot reload)
            try:
                current_mtime = os.path.getmtime(args.table)
                if current_mtime > last_table_mtime:
                    channels_obj = load_hv_table(args.table)
                    target_channels = {(ch.slot, ch.channel) for ch in channels_obj}
                    last_table_mtime = current_mtime
                    logging.info(f"Loaded {len(target_channels)} target valid channels from {args.table}")
            except Exception as e:
                logging.warning(f"Could not read {args.table}: {e}")

            try:
                server_alive = collect_and_write(
                    client, db, start_time,
                    cycle_count, error_count,
                    server_alive, target_channels)
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
