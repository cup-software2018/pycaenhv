import time
import curses
import sys
import argparse
from hvclient import HVClient
from hvchannel import HVChannel
import hvconfig


def load_hv_table(filepath):
    channels = []
    try:
        with open(filepath, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split()
                if len(parts) >= 7:
                    ch = HVChannel(
                        name=parts[0], slot=parts[1], channel=parts[2],
                        hv_set=parts[3], r_val=parts[4], pmtid=parts[5], group=parts[6]
                    )
                    channels.append(ch)
    except FileNotFoundError:
        print(f"Error: Could not find {filepath}")
        sys.exit(1)
    return channels


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


def _monitor_loop(stdscr, client, channels, group):
    stdscr.nodelay(True)
    while True:
        stdscr.clear()
        stdscr.addstr(
            f"=== HV Monitoring: Group '{group}' (Press 'q' to stop) ===\n\n")

        # Pull latest raw data from server
        raw_data = client.poll_data()

        if raw_data:
            # Match raw data with our table objects
            for ch in channels:
                if ch.group == group or group == "all":
                    # Find matching slot/ch in raw data
                    update = next((d for d in raw_data if d["slot"] == int(
                        ch.slot) and d["channel"] == int(ch.channel)), None)
                    if update:
                        ch.set_current_value(update["vmon"], update["imon"])
                        # This will use the name from the table
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
    parser.add_argument("-t", "--table", default="hv.table",
                        help=f"Path to the HV configuration table file (default: hv.table)")

    args = parser.parse_args()

    # 1. Load the local table
    fChannels = load_hv_table(args.table)

    # 2. Connect to Client and Check Server
    client = HVClient()
    if not client.check_server():
        print(f"Error: HV Server is not running. Please start hvserver.py first.")
        client.close()  # Must close ZMQ context before exit, otherwise process hangs
        sys.exit(1)

    # 3. Synchronize hardware with table settings
    sync_hardware(client, fChannels, args.group)

    # 4. Execute action
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
