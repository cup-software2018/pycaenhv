import zmq
import time
import json
import threading
import sys
import os
import signal
import logging
import argparse
from caenhv import CaenHV, SY4527, SY5527, N1470

# --- Default Constants ---
DEFAULT_IP = "192.168.0.152"
DEFAULT_SYS = SY5527
DEFAULT_CMD_PORT = 5555
DEFAULT_PUB_PORT = 5556
LOG_FILE = "hvserver.log"
PID_FILE = "hvserver.pid"

class HVServer:
    def __init__(self, ip=DEFAULT_IP, sys_type=DEFAULT_SYS, cmd_port=DEFAULT_CMD_PORT, pub_port=DEFAULT_PUB_PORT):
        self.ip = ip
        self.sys_type = sys_type
        self.cmd_port = cmd_port
        self.pub_port = pub_port
        
        # Internal state
        self.channels = []
        self.hv = CaenHV()
        self.context = zmq.Context()
        
        self.cmd_socket = self.context.socket(zmq.REP)
        self.cmd_socket.bind(f"tcp://*:{self.cmd_port}")
        
        self.pub_socket = self.context.socket(zmq.PUB)
        self.pub_socket.bind(f"tcp://*:{self.pub_port}")
        
        self.running = True
        self.monitor_thread = None

    def start(self):
        try:
            logging.info(f"Connecting to CAEN HV at {self.ip}...")
            self.hv.init_system(self.sys_type, self.ip, "admin", "admin")
            
            # Hardware discovery
            logging.info("Discovering hardware layout...")
            crate_map = self.hv.get_crate_map()
            self.channels = []
            for slot, ch_count in crate_map.items():
                for ch_idx in range(ch_count):
                    self.channels.append({
                        "slot": int(slot),
                        "channel": int(ch_idx)
                    })
            
            logging.info(f"Discovery complete: Found {len(crate_map)} active slots and {len(self.channels)} total channels.")
            
            # Start monitoring thread
            self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self.monitor_thread.start()
            
            logging.info(f"HV Server is fully operational.")
            logging.info(f"Listening for commands on port {self.cmd_port}")
            logging.info(f"Broadcasting telemetry on port {self.pub_port}")
            
            self._command_loop()
            
        except Exception as e:
            logging.error(f"Critical Startup Error: {e}")
            self.shutdown(f"Startup failed: {e}")

    def _monitor_loop(self):
        logging.debug("Starting background monitoring loop (1Hz)")
        while self.running:
            data_list = []
            try:
                for ch_info in self.channels:
                    slot = ch_info["slot"]
                    channel = ch_info["channel"]
                    
                    vmon = self.hv.get_vmon(slot, channel)
                    imon = self.hv.get_imon(slot, channel)
                    status = self.hv.get_status(slot, channel)
                    
                    data_list.append({
                        "slot": slot,
                        "channel": channel,
                        "vmon": vmon,
                        "imon": imon,
                        "status": status
                    })
                
                # Publish data
                self.pub_socket.send_json({"type": "update", "data": data_list})
                
            except Exception as e:
                logging.error(f"Hardware communication lost during monitor: {e}")
                self.shutdown(f"Hardware lost: {e}")
                break
                
            time.sleep(1)

    def _command_loop(self):
        poller = zmq.Poller()
        poller.register(self.cmd_socket, zmq.POLLIN)
        
        while self.running:
            if poller.poll(500): # 500ms timeout to keep loop responsive to shutdown flag
                try:
                    msg = self.cmd_socket.recv_json()
                    method = msg.get("method")
                    params = msg.get("params", [])
                    
                    logging.info(f"CMD Request: {method}({params})")
                    result = self._handle_request(method, params)
                    self.cmd_socket.send_json({"status": "ok", "result": result})
                except Exception as e:
                    logging.warning(f"Error handling request: {e}")
                    self.cmd_socket.send_json({"status": "error", "error": str(e)})

    def _handle_request(self, method, params):
        if method == "ping":
            return "pong"
        
        if method == "get_channels":
            return self.channels

        # Standard hardware commands
        if method == "turn_on":
            return self.hv.turn_on(*params)
        if method == "turn_off":
            return self.hv.turn_off(*params)
        if method == "set_vset":
            return self.hv.set_vset(*params)
        if method == "set_iset":
            return self.hv.set_iset(*params)
        if method == "set_name":
            return self.hv.set_name(*params)
        if method == "get_ch_param":
            return self.hv.get_ch_param(*params)

        raise ValueError(f"Unknown method: {method}")

    def shutdown(self, reason):
        if not self.running and not reason.startswith("Startup"):
            return # Already shutting down
            
        logging.info(f"Shutting down server. Reason: {reason}")
        self.running = False
        
        try:
            # Notify clients
            self.pub_socket.send_json({"type": "shutdown", "reason": reason}, flags=zmq.NOBLOCK)
            time.sleep(0.5) 
            
            # Close hardware
            if self.hv.is_connected:
                self.hv.deinit_system()
                logging.info("CAEN System deinitialized.")
        except Exception as e:
            logging.error(f"Error during shutdown: {e}")
            
        self.context.term()
        logging.info("Server process terminated.")
        
        # Cleanup PID file if we are the owner
        if os.path.exists(PID_FILE):
            try:
                with open(PID_FILE, 'r') as f:
                    pid = int(f.read().strip())
                if pid == os.getpid():
                    os.remove(PID_FILE)
            except:
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
    parser.add_argument("--ip", default=DEFAULT_IP, help=f"CAEN Mainframe IP (default: {DEFAULT_IP})")
    parser.add_argument("--sys", type=int, default=DEFAULT_SYS, help=f"System type 2=SY4527, 3=SY5527 (default: {DEFAULT_SYS})")
    parser.add_argument("--cmd-port", type=int, default=DEFAULT_CMD_PORT, help="Command port (REP)")
    parser.add_argument("--pub-port", type=int, default=DEFAULT_PUB_PORT, help="Telemetry port (PUB)")
    parser.add_argument("--daemon", action="store_true", help="Run in background (daemonize)")
    parser.add_argument("--log", default=LOG_FILE, help=f"Log file path (default: {LOG_FILE})")
    parser.add_argument("--pid", default=PID_FILE, help=f"PID file path (default: {PID_FILE})")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

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
    global PID_FILE
    PID_FILE = args.pid
    with open(args.pid, 'w') as f:
        f.write(str(os.getpid()))

    server = HVServer(ip=args.ip, sys_type=args.sys, cmd_port=args.cmd_port, pub_port=args.pub_port)

    # Signal handlers
    def signal_handler(sig, frame):
        reason = "Cought SIGNAL " + ("SIGINT" if sig == signal.SIGINT else "SIGTERM")
        server.shutdown(reason)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    server.start()

if __name__ == "__main__":
    main()
