# hvchannel.py

class HVChannel:
    def __init__(self, name, slot, channel, hv_set, r_val, pmtid, group):
        self.name = name
        self.slot = int(slot)
        self.channel = int(channel)
        self.hv_set = float(hv_set)
        self.r_val = float(r_val)
        self.pmtid = int(pmtid)
        self.group = str(group)

        # Monitored values
        self.vmon = 0.0
        self.imon = 0.0

    def set_current_value(self, vcur, icur):
        self.vmon = vcur
        self.imon = icur

    def print_info(self, stdscr=None):
        info_str = (f"[{self.group: >2}] {self.name: <5} (S:{self.slot: <2} C:{self.channel: <2}) "
                    f"| Set: {self.hv_set:6.1f}V | VMon: {self.vmon:7.2f} V | IMon: {self.imon:7.2f} uA")
        if stdscr:
            stdscr.addstr(info_str + "\n")
        else:
            print(info_str)

def load_hv_table(filepath):
    """
    Parses the hv.table text file and returns a list of HVChannel objects.
    Line format: Name Slot Channel VSet R(MOhm) PMTID Group
    """
    channels = []
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
    return channels
