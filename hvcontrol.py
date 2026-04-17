import time
import curses
import sys
import argparse
from datetime import datetime
from hvclient import HVClient
from hvchannel import HVChannel, load_hv_table
import hvconfig



def sync_hardware(client, channels, group="all"):
    """
    Push names and calculated I-limits to the server for channels in the table.
    """
    print(f"Synchronizing hardware settings for group '{group}'...")
    for ch in channels:
        if ch.group == group or group == "all":
            # Calculate current limit in uA
            i_set = ch.hv_set / ch.r_val
            i_limit = i_set * 1.1

            # Push voltage and current limit (critical)
            client.send_command("set_vset", int(ch.slot),
                                int(ch.channel), float(ch.hv_set))
            client.send_command("set_iset", int(ch.slot),
                                int(ch.channel), float(i_limit))

            # Push channel name (best-effort: some boards do not support this)
            try:
                client.send_command("set_name", int(ch.slot),
                                    int(ch.channel), ch.name)
            except Exception:
                pass


def _server_status_str(client) -> str:
    """Return a combined server and hardware status string for display."""
    try:
        health = client.get_server_health(timeout_ms=500)
        caen_connected = health.get("caen_connected", False)
        hw_str = "ON" if caen_connected else "OFF (waiting)"
        return f"Server: ON  |  CAEN Hardware: {hw_str}"
    except Exception:
        return "Server: OFF (Unreachable)  |  CAEN Hardware: UNKNOWN"


def _monitor_loop(stdscr, client, channels, group):
    stdscr.nodelay(True)
    while True:
        stdscr.clear()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status  = _server_status_str(client)
        stdscr.addstr(
            f"=== HV Monitoring: Group '{group}'  [{now_str}] ===\n"
            f"=== {status}   (Press 'q' to stop) ===\n\n")

        # Pull latest raw data from server
        raw_data = client.poll_data()

        if raw_data:
            # Match raw data with our table objects
            for ch in channels:
                if ch.group == group or group == "all":
                    update = next((d for d in raw_data if d["slot"] == int(
                        ch.slot) and d["channel"] == int(ch.channel)), None)
                    if update:
                        ch.set_current_value(update["vmon"], update["imon"])
                        ch.print_info(stdscr)
        else:
            stdscr.addstr("Waiting for data from server...\n")

        stdscr.refresh()

        try:
            key = stdscr.getkey()
            if key in ['q', 'Q']:
                break
        except curses.error:
            pass

        time.sleep(1)


def monitoring(client, channels, group):
    curses.wrapper(_monitor_loop, client, channels, group)


def main():
    # Setup command line argument parsing
    parser = argparse.ArgumentParser(
        description="CAEN HV Control & Monitoring Tool (Local Only)")

    # Positional argument: Action
    parser.add_argument("action", choices=['mon', 'on', 'off'],
                        help="Action to perform: mon(Monitor), on(Power On), off(Power Off)")

    # Optional arguments
    parser.add_argument("-g", "--group", default="all",
                        help="Target group name from the table (default: all)")
    parser.add_argument("-t", "--table", default=hvconfig.HV_TABLE,
                        help=f"Path to the HV configuration table file (default: {hvconfig.HV_TABLE})")

    args = parser.parse_args()

    # 1. Load the local table
    fChannels = load_hv_table(args.table)

    # 2. Connect and check server
    client = HVClient()
    if not client.check_server():
        print("Error: HV Server is not running. Please start hvserver.py first.")
        client.close()
        sys.exit(1)

    # 3. Get server health to determine hardware connectivity
    try:
        health   = client.get_server_health()
        caen_connected = health.get("caen_connected", False)
    except Exception:
        caen_connected = False

    if caen_connected:
        # 4a. Sync hardware settings and execute action
        sync_hardware(client, fChannels, args.group)
    else:
        # 4b. Degraded mode: skip sync, warn user
        print("Warning: Server is DEGRADED (waiting for CAEN hardware). Sync skipped.")
        print("Monitoring only — on/off commands will be blocked until hardware reconnects.\n")
        if args.action in ['on', 'off']:
            print(f"Cannot execute '{args.action}': server hardware not ready.")
            print("Switching to monitoring mode instead.")
            args.action = 'mon'

    # 5. Execute action
    if args.action == 'mon':
        monitoring(client, fChannels, args.group)

    elif args.action == 'on':
        print(f"Turning ON group '{args.group}'...")
        for ch in fChannels:
            if ch.group == args.group or args.group == "all":
                client.send_command("turn_on", int(ch.slot), int(ch.channel))
        print("Command sent. Switching to monitoring...")
        time.sleep(1)
        monitoring(client, fChannels, args.group)

    elif args.action == 'off':
        print(f"Turning OFF group '{args.group}'...")
        for ch in fChannels:
            if ch.group == args.group or args.group == "all":
                client.send_command("turn_off", int(ch.slot), int(ch.channel))
        print("Command sent. Switching to monitoring...")
        time.sleep(1)
        monitoring(client, fChannels, args.group)


if __name__ == "__main__":
    main()
