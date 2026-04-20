#!/usr/bin/env python3
# hvtweak.py
# A simple standalone tool to control a single CAEN HV channel for calibration and testing.

import argparse
import sys
import time
from caenhv import CaenHV


def main():
    parser = argparse.ArgumentParser(
        description="Directly tweak a single CAEN HV channel without needing hvserver")
    parser.add_argument("slot", type=int, help="Hardware slot number")
    parser.add_argument("channel", type=int, help="Channel number")

    parser.add_argument("-V", "--vset", type=float, help="Set voltage (V)")
    parser.add_argument("-I", "--iset", type=float,
                        help="Set current limit (uA)")

    # Mutually exclusive flags for power control
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--on", action="store_true", help="Turn channel ON")
    group.add_argument("--off", action="store_true", help="Turn channel OFF")

    parser.add_argument("-a", "--ip", default="", help="CAEN Crate IP Address")
    parser.add_argument("-t", "--type", type=int, default=2,
                        help="System Type (2=SY4527, 3=SY5527) (default: 2)")
    parser.add_argument("-u", "--user", default="admin",
                        help="Login Username (default: admin)")
    parser.add_argument("-p", "--passw", default="admin",
                        help="Login Password (default: admin)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Enable verbose status output")

    args = parser.parse_args()

    def vprint(*a, **kw):
        if args.verbose:
            print(*a, **kw)

    hv = CaenHV()
    vprint(f"Connecting directly to CAEN Crate at {args.ip}...")
    try:
        hv.init_system(args.type, args.ip, args.user, args.passw)
    except Exception as e:
        print(f"Connection Error: {e}")
        sys.exit(1)

    vprint(f"=== Manipulating Slot {args.slot} Channel {args.channel} ===")

    try:
        no_action = (
            args.vset is None and args.iset is None and not args.on and not args.off)

        # 1. Apply Settings
        if no_action:
            vprint("No action requested. Fetching current status...\n")
        else:
            if args.vset is not None:
                vprint(f" -> Setting V0Set = {args.vset} V")
                hv.set_vset(args.slot, args.channel, args.vset)

            if args.iset is not None:
                vprint(f" -> Setting I0Set = {args.iset} uA")
                hv.set_iset(args.slot, args.channel, args.iset)

            if args.on:
                vprint(" -> Turning ON...")
                hv.turn_on(args.slot, args.channel)
            elif args.off:
                vprint(" -> Turning OFF...")
                hv.turn_off(args.slot, args.channel)

            vprint("Commands sent successfully!\n")
            if args.verbose:
                time.sleep(0.5)

        # 2. Synchronous Readback (only if no action was given, OR if verbose is enabled)
        if no_action or args.verbose:
            vprint("Reading latest telemetry from hardware...")
            vmon = hv.get_ch_param(args.slot, args.channel, "VMon")
            imon = hv.get_ch_param(args.slot, args.channel, "IMon")
            status_val = hv.get_status(args.slot, args.channel)

            is_on = bool(status_val & (1 << 0))
            is_ramping = bool(status_val & ((1 << 1) | (1 << 2)))
            is_trip = bool(status_val & (1 << 8))

            state = "RUNNING/ON" if is_on else "OFF"
            if is_trip:
                state = "TRIPPED"
            elif is_ramping:
                state = "RAMPING"

            vprint(f"\n--- Current Status of [S:{args.slot} C:{args.channel}] ---")
            vprint(f" State: {state} (Raw status int: {status_val})")
            vprint(f" VMon:  {vmon:.2f} V")
            vprint(f" IMon:  {imon:.2f} uA")
            vprint("-----------------------------------------")

    except Exception as e:
        print(f"Execution Error: {e}")

    finally:
        if hv.is_connected:
            hv.deinit_system()


if __name__ == "__main__":
    main()
