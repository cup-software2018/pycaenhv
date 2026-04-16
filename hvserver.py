import zmq
import time
import threading
import sys
import os
import signal
import logging
import argparse
import hvconfig
from caenhv import CaenHV

class HVServer:
    def __init__(self, ip=hvconfig.IP_ADDRESS, sys_type=hvconfig.SYSTEM_TYPE,
                 cmd_port=hvconfig.CMD_PORT, pub_port=hvconfig.PUB_PORT,
                 pid_file=None, reconnect_interval=None):
        self.ip = ip
        self.sys_type = sys_type
        self.cmd_port = cmd_port
        self.pub_port = pub_port
        self.pid_file = pid_file
        self.reconnect_interval = reconnect_interval or hvconfig.RECONNECT_INTERVAL

        # Internal state
        self.channels = []
        self.hv = CaenHV()
        self.context = zmq.Context()

        self.cmd_socket = self.context.socket(zmq.REP)
        self.cmd_socket.bind(f"tcp://*:{self.cmd_port}")

        self.pub_socket = self.context.socket(zmq.PUB)
        self.pub_socket.bind(f"tcp://*:{self.pub_port}")

        self.running        = True
        self.caen_connected = False   # True when hardware is connected and usable
        self.monitor_thread   = None
        self.reconnect_thread = None
        self.start_time  = time.monotonic()
        self.error_count = 0

    # ------------------------------------------------------------------
    # Hardware connection helpers
    # ------------------------------------------------------------------

    def _connect_hardware(self) -> bool:
        """
        Attempt to connect and discover CAEN hardware.
        Returns True on success, False on failure.
        Thread-safe: called from both start() and _reconnect_loop().
        """
        try:
            logging.info(f"Connecting to CAEN HV at {self.ip}...")
            self.hv.init_system(self.sys_type, self.ip,
                                hvconfig.USERNAME, hvconfig.PASSWORD)

            logging.info("Discovering hardware layout...")
            crate_map = self.hv.get_crate_map()
            channels = []
            for slot, ch_count in crate_map.items():
                for ch_idx in range(ch_count):
                    channels.append({"slot": int(slot), "channel": int(ch_idx)})

            self.channels = channels
            self.caen_connected = True
            logging.info(
                f"Hardware connected: {len(crate_map)} slots, "
                f"{len(self.channels)} channels."
            )
            return True

        except Exception as e:
            self.caen_connected = False
            logging.warning(f"Hardware connection failed: {e}")
            return False

    def _reconnect_loop(self):
        """
        Background thread: periodically retry hardware when in degraded state.
        On success, starts / restarts the monitor thread.
        """
        while self.running:
            # Sleep in short steps so shutdown is responsive
            deadline = time.monotonic() + self.reconnect_interval
            while self.running and time.monotonic() < deadline:
                time.sleep(0.5)

            if not self.running:
                break

            if not self.caen_connected:
                logging.info("Retrying hardware connection...")
                if self._connect_hardware():
                    # Restart monitor thread if not alive
                    if (self.monitor_thread is None
                            or not self.monitor_thread.is_alive()):
                        self.monitor_thread = threading.Thread(
                            target=self._monitor_loop, daemon=True)
                        self.monitor_thread.start()
                        logging.info("Monitor thread restarted.")

    # ------------------------------------------------------------------
    # Main startup
    # ------------------------------------------------------------------

    def start(self):
        # ZMQ sockets are already bound in __init__ — server is "alive" here.
        logging.info(f"Listening for commands on port {self.cmd_port}")
        logging.info(f"Broadcasting telemetry on port {self.pub_port}")

        # Initial hardware connection attempt
        if self._connect_hardware():
            # Start monitor thread immediately
            self.monitor_thread = threading.Thread(
                target=self._monitor_loop, daemon=True)
            self.monitor_thread.start()
            logging.info("HV Server is fully operational.")
        else:
            logging.warning(
                "Starting in DEGRADED mode — hardware not reachable. "
                f"Will retry every {self.reconnect_interval:.0f}s."
            )

        # Reconnect thread always runs (handles both initial failure and mid-run loss)
        self.reconnect_thread = threading.Thread(
            target=self._reconnect_loop, daemon=True)
        self.reconnect_thread.start()

        self._command_loop()

    # ------------------------------------------------------------------
    # Background monitor loop (1 Hz telemetry publish)
    # ------------------------------------------------------------------

    def _monitor_loop(self):
        logging.debug("Monitor loop started (1 Hz)")
        while self.running and self.caen_connected:
            data_list = []
            try:
                for ch_info in self.channels:
                    slot    = ch_info["slot"]
                    channel = ch_info["channel"]
                    data_list.append({
                        "slot":    slot,
                        "channel": channel,
                        "vmon":    self.hv.get_vmon(slot, channel),
                        "imon":    self.hv.get_imon(slot, channel),
                        "status":  self.hv.get_status(slot, channel),
                    })

                self.pub_socket.send_json({"type": "update", "data": data_list})

            except Exception as e:
                self.error_count += 1
                self.caen_connected = False
                logging.error(
                    f"Hardware communication lost (errors={self.error_count}): {e}. "
                    f"Entering degraded mode; reconnect thread will retry."
                )
                break   # exit loop — reconnect_loop will restart us

            time.sleep(1)
        logging.debug("Monitor loop exited.")

    # ------------------------------------------------------------------
    # Command loop & request dispatch
    # ------------------------------------------------------------------

    def _command_loop(self):
        poller = zmq.Poller()
        poller.register(self.cmd_socket, zmq.POLLIN)

        while self.running:
            if poller.poll(500):
                try:
                    msg    = self.cmd_socket.recv_json()
                    method = msg.get("method")
                    params = msg.get("params", [])

                    logging.debug(f"CMD: {method}({params})")
                    result = self._handle_request(method, params)
                    self.cmd_socket.send_json({"status": "ok", "result": result})
                except Exception as e:
                    logging.warning(f"Error handling request: {e}")
                    self.cmd_socket.send_json({"status": "error", "error": str(e)})

    def _handle_request(self, method, params):
        # Always available regardless of hw_state
        if method == "ping":
            return "pong"

        if method == "get_server_health":
            return {
                "uptime_s":       time.monotonic() - self.start_time,
                "caen_connected": self.caen_connected,
                "channel_count":  len(self.channels),
                "error_count":    self.error_count,
            }

        if method == "get_channels":
            return self.channels

        # Hardware commands — blocked in degraded mode
        if not self.caen_connected:
            raise RuntimeError("Server is in DEGRADED mode: hardware not connected")

        if method == "turn_on":     return self.hv.turn_on(*params)
        if method == "turn_off":    return self.hv.turn_off(*params)
        if method == "set_vset":    return self.hv.set_vset(*params)
        if method == "set_iset":    return self.hv.set_iset(*params)
        if method == "set_name":    return self.hv.set_name(*params)
        if method == "get_ch_param":return self.hv.get_ch_param(*params)

        raise ValueError(f"Unknown method: {method}")

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def shutdown(self, reason):
        if not self.running:
            return

        logging.info(f"Shutting down server. Reason: {reason}")
        self.running = False

        try:
            self.pub_socket.send_json(
                {"type": "shutdown", "reason": reason}, flags=zmq.NOBLOCK)
            time.sleep(0.5)

            if self.hv.is_connected:
                self.hv.deinit_system()
                logging.info("CAEN system deinitialized.")
        except Exception as e:
            logging.error(f"Error during shutdown: {e}")

        self.context.term()
        logging.info("Server process terminated.")

        pid_path = self.pid_file
        if pid_path and os.path.exists(pid_path):
            try:
                with open(pid_path, 'r') as f:
                    if int(f.read().strip()) == os.getpid():
                        os.remove(pid_path)
            except Exception:
                pass

        sys.exit(0)

def daemonize():
    """Standard double-fork daemonization."""
    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0) # Exit first parent
    except OSError as e:
        sys.stderr.write(f"Fork #1 failed: {e}\n")
        sys.exit(1)

    os.chdir("/")
    os.setsid()
    os.umask(0)

    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0) # Exit second parent
    except OSError as e:
        sys.stderr.write(f"Fork #2 failed: {e}\n")
        sys.exit(1)

    # Redirect standard file descriptors
    sys.stdout.flush()
    sys.stderr.flush()
    with open('/dev/null', 'r') as f:
        os.dup2(f.fileno(), sys.stdin.fileno())
    with open('/dev/null', 'a+') as f:
        os.dup2(f.fileno(), sys.stdout.fileno())
    with open('/dev/null', 'a+') as f:
        os.dup2(f.fileno(), sys.stderr.fileno())

def main():
    parser = argparse.ArgumentParser(description="CAEN HV Background Server (Daemon)")
    parser.add_argument("--ip", default=hvconfig.IP_ADDRESS, help=f"CAEN Mainframe IP (default: {hvconfig.IP_ADDRESS})")
    parser.add_argument("--sys", type=int, default=hvconfig.SYSTEM_TYPE, help=f"System type 2=SY4527, 3=SY5527 (default: {hvconfig.SYSTEM_TYPE})")
    parser.add_argument("--cmd-port", type=int, default=hvconfig.CMD_PORT, help="Command port (REP)")
    parser.add_argument("--pub-port", type=int, default=hvconfig.PUB_PORT, help="Telemetry port (PUB)")
    parser.add_argument("--daemon", action="store_true", help="Run in background (daemonize)")
    parser.add_argument("--log", default=hvconfig.SERVER_LOG_FILE, help=f"Log file path (default: {hvconfig.SERVER_LOG_FILE})")
    parser.add_argument("--pid", default=hvconfig.SERVER_PID_FILE, help=f"PID file path (default: {hvconfig.SERVER_PID_FILE})")

    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    # Resolve to absolute paths NOW, before daemonize() calls os.chdir("/")
    args.log = os.path.abspath(args.log)
    args.pid = os.path.abspath(args.pid)

    # Configure logging
    log_level = logging.DEBUG if args.debug else logging.INFO
    log_handlers = [logging.FileHandler(args.log)]
    if not args.daemon:
        log_handlers.append(logging.StreamHandler())

    logging.basicConfig(
        level=log_level,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=log_handlers
    )

    # Check for existing PID file
    if os.path.exists(args.pid):
        try:
            with open(args.pid, 'r') as f:
                old_pid = int(f.read().strip())
            # Check if process is actually running
            os.kill(old_pid, 0)
            logging.error(f"Server is already running with PID {old_pid}. Exiting.")
            sys.exit(1)
        except (OSError, ValueError):
            # Process not running or PID file corrupt
            logging.warning("Stale PID file found. Cleaning up.")
            os.remove(args.pid)

    if args.daemon:
        logging.info("Daemonizing server...")
        daemonize()

    # Write new PID file
    with open(args.pid, 'w') as f:
        f.write(str(os.getpid()))

    server = HVServer(ip=args.ip, sys_type=args.sys,
                      cmd_port=args.cmd_port, pub_port=args.pub_port,
                      pid_file=args.pid)

    # Signal handlers
    def signal_handler(sig, frame):
        reason = "Caught SIGNAL " + ("SIGINT" if sig == signal.SIGINT else "SIGTERM")
        server.shutdown(reason)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    server.start()

if __name__ == "__main__":
    main()
