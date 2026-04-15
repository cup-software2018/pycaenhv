import time
import curses
import sys
import argparse
from caenhv import CaenHV
from hvchannel import HVChannel
import hvconfig

CAENSYS = hvconfig.SYSTEM_TYPE
IPADDR = hvconfig.IP_ADDRESS
USERNAME = hvconfig.USERNAME
PASSWORD = hvconfig.PASSWORD


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


def power_on(hv, channels, group):
    for ch in channels:
        if ch.group == group or group == "all":
            hv.turn_on(ch.slot, ch.channel)


def power_off(hv, channels, group):
    for ch in channels:
        if ch.group == group or group == "all":
            hv.turn_off(ch.slot, ch.channel)


def apply_hv_settings(hv, channels, group):
    # Set the V0Set and I0Set parameters for channels based on the table
    for ch in channels:
        if ch.group == group or group == "all":
            # Calculate current in uA (V in Volts / R in MOhms = I in uA)
            i_set = ch.hv_set / ch.r_val

            # Add a 10% safety margin to prevent nuisance tripping (optional but recommended)
            i_limit = i_set * 1.1

            # Apply Voltage, Current, and Name settings
            hv.set_vset(ch.slot, ch.channel, ch.hv_set)
            hv.set_iset(ch.slot, ch.channel, i_limit)
            hv.set_name(ch.slot, ch.channel, ch.name)


def _monitor_loop(stdscr, hv, channels, group):
    stdscr.nodelay(True)
    while True:
        stdscr.clear()
        stdscr.addstr(
            f"=== HV Monitoring: Group '{group}' (Press 'q' to stop) ===\n\n")

        for ch in channels:
            if ch.group == group or group == "all":
                try:
                    vcur = hv.get_vmon(ch.slot, ch.channel)
                    icur = hv.get_imon(ch.slot, ch.channel)
                    ch.set_current_value(vcur, icur)
                    ch.print_info(stdscr)
                except Exception as e:
                    stdscr.addstr(f"Error reading {ch.name}: {e}\n")

        stdscr.refresh()

        try:
            key = stdscr.getkey()
            if key in ['q', 'Q']:
                break
        except curses.error:
            pass

        time.sleep(1)


def monitoring(hv, channels, group):
    curses.wrapper(_monitor_loop, hv, channels, group)


def main():
    # Setup command line argument parsing
    parser = argparse.ArgumentParser(
        description="CAEN HV Control & Monitoring Tool")

    # Positional argument: Action
    parser.add_argument("action", choices=['mon', 'on', 'off'],
                        help="Action to perform: mon(Monitor), on(Power On), off(Power Off)")

    # Optional arguments
    parser.add_argument("-g", "--group", default="all",
                        help="Target group name from the table (default: all)")
    parser.add_argument("-t", "--table", default="hv.table",
                        help="Path to the HV configuration table file")

    args = parser.parse_args()

    # 1. Load the table
    fChannels = load_hv_table(args.table)

    # 2. Validate group parameter
    if args.group != "all":
        group_exists = any(ch.group == args.group for ch in fChannels)
        if not group_exists:
            print(f"Error: Group '{args.group}' not found in {args.table}.")
            sys.exit(1)

    # 3. Connect and execute action
    with CaenHV() as hv:
        try:
            hv.init_system(CAENSYS, IPADDR, USERNAME, PASSWORD)

            # Automatically synchronize hardware with table settings (all channels)
            print(
                f"Synchronizing hardware with {args.table} for ALL groups...")
            apply_hv_settings(hv, fChannels, "all")
        except Exception as e:
            print(f"Failed to connect or sync with {IPADDR}: {e}")
            sys.exit(1)

        if args.action == 'mon':
            # Start monitoring immediately
            monitoring(hv, fChannels, args.group)

        elif args.action == 'on':
            # Power ON and then switch to monitor
            print(f"Turning ON group '{args.group}'...")
            power_on(hv, fChannels, args.group)
            print("Command sent. Switching to monitoring...")
            time.sleep(1)  # Brief pause to show the message
            monitoring(hv, fChannels, args.group)

        elif args.action == 'off':
            # Power OFF and then switch to monitor
            print(f"Turning OFF group '{args.group}'...")
            power_off(hv, fChannels, args.group)
            print("Command sent. Switching to monitoring...")
            time.sleep(1)  # Brief pause to show the message
            monitoring(hv, fChannels, args.group)


if __name__ == "__main__":
    main()
