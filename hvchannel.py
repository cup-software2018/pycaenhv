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
