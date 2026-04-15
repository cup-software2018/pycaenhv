#!/usr/bin/env python3
"""
caen_probe.py - Probe a CAEN HV mainframe and print all active slots and channels.
Usage: python caen_probe.py [--ip IP] [--sys SYS_TYPE]
"""

import argparse
import sys
import hvconfig
from caenhv import CaenHV

def probe(ip, sys_type):
    hv = CaenHV()
    print(f"Connecting to CAEN HV at {ip} ...")
    try:
        hv.init_system(sys_type, ip, hvconfig.USERNAME, hvconfig.PASSWORD)
    except Exception as e:
        print(f"  ERROR: {e}")
        sys.exit(1)

    print("  Connected.\n")
    print("Discovering crate map ...")
    try:
        crate_map = hv.get_crate_map()
    except Exception as e:
        print(f"  ERROR: {e}")
        hv.deinit_system()
        sys.exit(1)

    if not crate_map:
        print("  No active slots found.")
    else:
        total_ch = sum(crate_map.values())
        print(f"  Found {len(crate_map)} active slot(s), {total_ch} total channel(s).\n")
        print(f"  {'Slot':>6}  {'Channels':>8}")
        print(f"  {'------':>6}  {'--------':>8}")
        for slot, ch_count in sorted(crate_map.items()):
            channels = ", ".join(str(c) for c in range(ch_count))
            print(f"  {slot:>6}  {ch_count:>8}  [ {channels} ]")

    print("\nDisconnecting ...")
    hv.deinit_system()
    print("  Done.")


def main():
    parser = argparse.ArgumentParser(description="Probe CAEN HV mainframe for active slots and channels.")
    parser.add_argument("--ip", default=hvconfig.IP_ADDRESS,
                        help=f"CAEN Mainframe IP (default: {hvconfig.IP_ADDRESS})")
    parser.add_argument("--sys", type=int, default=hvconfig.SYSTEM_TYPE,
                        help=f"System type: 2=SY4527, 3=SY5527, 6=N1470 (default: {hvconfig.SYSTEM_TYPE})")
    args = parser.parse_args()

    probe(args.ip, args.sys)


if __name__ == "__main__":
    main()
