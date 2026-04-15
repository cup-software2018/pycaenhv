# hvclient.py
import zmq
import time
import hvconfig


class HVClient:
    def __init__(self, cmd_url=None, sub_url=None):
        host = "localhost"
        self.cmd_url = cmd_url if cmd_url else f"tcp://{host}:{hvconfig.CMD_PORT}"
        self.sub_url = sub_url if sub_url else f"tcp://{host}:{hvconfig.PUB_PORT}"

        # Save URL for reconnection in case of timeout
        self.context = zmq.Context()
        self.cmd_socket = self.context.socket(zmq.REQ)
        self.cmd_socket.connect(self.cmd_url)

        self.sub_socket = self.context.socket(zmq.SUB)
        self.sub_socket.connect(self.sub_url)
        self.sub_socket.setsockopt_string(zmq.SUBSCRIBE, "")

        self.latest_data = None

    def check_server(self, timeout_ms=1000):
        """
        Sends a heartbeat request to verify the server is alive with a timeout.
        """
        poller = zmq.Poller()
        poller.register(self.cmd_socket, zmq.POLLIN)

        try:
            # Send ping
            self.cmd_socket.send_json({"method": "ping"})

            # Wait for reply with timeout
            if poller.poll(timeout_ms):
                reply = self.cmd_socket.recv_json()
                return reply.get("status") == "ok"
            else:
                # Recreate socket to clear the blocked REQ state
                self.cmd_socket.close()
                self.cmd_socket = self.context.socket(zmq.REQ)
                self.cmd_socket.connect(self.cmd_url)
                return False
        except Exception:
            return False

    def send_command(self, method, *args, timeout_ms=2000):
        """
        Sends a command to the server and waits for a reply with a timeout to prevent GUI freezing.
        """
        self.cmd_socket.send_json({"method": method, "params": args})

        poller = zmq.Poller()
        poller.register(self.cmd_socket, zmq.POLLIN)

        if poller.poll(timeout_ms):
            reply = self.cmd_socket.recv_json()
            if reply.get("status") == "error":
                raise RuntimeError(reply.get("error"))
            return reply.get("result")
        else:
            # Recreate the REQ socket to recover from timeout state
            self.cmd_socket.close()
            self.cmd_socket = self.context.socket(zmq.REQ)
            self.cmd_socket.connect(self.cmd_url)
            raise TimeoutError(
                f"Server did not respond to '{method}' within {timeout_ms}ms")

    def poll_data(self):
        """
        Pulls all available messages from the SUB socket and keeps the latest.
        """
        while True:
            try:
                # Use NOBLOCK to pull all pending messages
                msg = self.sub_socket.recv_json(flags=zmq.NOBLOCK)
                if msg.get("type") == "update":
                    self.latest_data = msg.get("data")
                elif msg.get("type") == "shutdown":
                    raise RuntimeError(
                        "Server is shutting down: " + msg.get("reason", "Unknown"))
            except zmq.Again:
                break
        return self.latest_data

    def close(self):
        self.cmd_socket.close()
        self.sub_socket.close()
        self.context.term()
