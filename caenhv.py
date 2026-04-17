import ctypes
from ctypes import c_int, c_char_p, c_void_p, c_ushort, c_float, c_short, c_ubyte, byref, cast, POINTER
from ctypes.util import find_library
import os

# CAEN System Constants
SY1527 = 0
SY2527 = 1
SY4527 = 2
SY5527 = 3
N1470 = 6
LINKTYPE_TCPIP = 0


class CaenHV:
    def __init__(self, lib_name="caenhvwrapper"):
        lib_path = find_library(lib_name)
        if not lib_path:
            lib_path = f"lib{lib_name}.so"

        # Load the shared library
        try:
            self._lib = ctypes.CDLL(lib_path)
        except OSError as e:
            raise RuntimeError(
                f"Failed to load library '{lib_path}'.\n"
                "Please ensure the library is installed and its directory is added to LD_LIBRARY_PATH.\n"
                f"Original Error: {e}"
            )

        # Connection handle
        self.handle = c_int(-1)
        self.is_connected = False

        # Register C function signatures
        self._register_functions()

    def _register_functions(self):
        # Bind CAENHV_InitSystem
        self._lib.CAENHV_InitSystem.argtypes = [
            c_int, c_int, c_void_p, c_char_p, c_char_p, POINTER(c_int)
        ]
        self._lib.CAENHV_InitSystem.restype = c_int

        # Bind CAENHV_DeinitSystem
        self._lib.CAENHV_DeinitSystem.argtypes = [c_int]
        self._lib.CAENHV_DeinitSystem.restype = c_int

        # Bind CAENHV_GetChParam
        self._lib.CAENHV_GetChParam.argtypes = [
            c_int, c_ushort, c_char_p, c_ushort, POINTER(c_ushort), c_void_p
        ]
        self._lib.CAENHV_GetChParam.restype = c_int

        # Bind CAENHV_SetChParam
        self._lib.CAENHV_SetChParam.argtypes = [
            c_int, c_ushort, c_char_p, c_ushort, POINTER(c_ushort), c_void_p
        ]
        self._lib.CAENHV_SetChParam.restype = c_int

        # Bind CAENHV_GetError
        self._lib.CAENHV_GetError.argtypes = [c_int]
        self._lib.CAENHV_GetError.restype = c_char_p

        # Bind CAENHV_GetCrateMap
        self._lib.CAENHV_GetCrateMap.argtypes = [
            c_int,
            POINTER(c_ushort),
            POINTER(POINTER(c_ushort)),
            POINTER(c_char_p),
            POINTER(c_char_p),
            POINTER(POINTER(c_ushort)),
            POINTER(POINTER(c_ubyte)),
            POINTER(POINTER(c_ubyte))
        ]
        self._lib.CAENHV_GetCrateMap.restype = c_int

        # Bind CAENHV_Free
        self._lib.CAENHV_Free.argtypes = [c_void_p]
        self._lib.CAENHV_Free.restype = c_int

    def init_system(self, system_type, ip_address, username="admin", password="admin"):
        # Convert strings to C char pointers
        c_ip = c_char_p(ip_address.encode('utf-8'))
        c_user = c_char_p(username.encode('utf-8'))
        c_pwd = c_char_p(password.encode('utf-8'))

        result = self._lib.CAENHV_InitSystem(
            system_type, LINKTYPE_TCPIP, c_ip, c_user, c_pwd, byref(
                self.handle)
        )

        if result == 0:
            self.is_connected = True
            return self.handle.value
        else:
            raise Exception(
                f"Connection failed (Error Code: {result} / {hex(result)}): {self.get_error()}")

    def deinit_system(self):
        if not self.is_connected:
            return 0

        result = self._lib.CAENHV_DeinitSystem(self.handle.value)
        if result == 0:
            self.is_connected = False
            self.handle = c_int(-1)
            return 0
        else:
            raise Exception(f"Disconnection failed: {self.get_error()}")

    def get_error(self):
        # Fetch the error message string from the library
        err_bytes = self._lib.CAENHV_GetError(self.handle.value)
        return err_bytes.decode('utf-8') if err_bytes else "Unknown Error"

    def get_crate_map(self):
        """
        Returns a dictionary mapping slot index to the number of channels it has.
        """
        if not self.is_connected:
            raise Exception("System not initialized")

        c_nr_slot = c_ushort(0)
        c_nr_ch_list = POINTER(c_ushort)()
        c_model_list = c_char_p()
        c_desc_list = c_char_p()
        c_ser_num_list = POINTER(c_ushort)()
        c_fmw_rel_min_list = POINTER(c_ubyte)()
        c_fmw_rel_max_list = POINTER(c_ubyte)()

        result = self._lib.CAENHV_GetCrateMap(
            self.handle.value,
            byref(c_nr_slot),
            byref(c_nr_ch_list),
            byref(c_model_list),
            byref(c_desc_list),
            byref(c_ser_num_list),
            byref(c_fmw_rel_min_list),
            byref(c_fmw_rel_max_list)
        )

        if result != 0:
            raise Exception(f"Failed to get crate map: {self.get_error()}")

        crate_map = {}
        nr_slots = c_nr_slot.value

        if nr_slots > 0 and bool(c_nr_ch_list):
            for i in range(nr_slots):
                ch_count = c_nr_ch_list[i]
                if ch_count > 0:
                    crate_map[i] = ch_count

        if bool(c_nr_ch_list):
            self._lib.CAENHV_Free(cast(c_nr_ch_list, c_void_p))
        if c_model_list.value:
            self._lib.CAENHV_Free(cast(c_model_list, c_void_p))
        if c_desc_list.value:
            self._lib.CAENHV_Free(cast(c_desc_list, c_void_p))
        if bool(c_ser_num_list):
            self._lib.CAENHV_Free(cast(c_ser_num_list, c_void_p))
        if bool(c_fmw_rel_min_list):
            self._lib.CAENHV_Free(cast(c_fmw_rel_min_list, c_void_p))
        if bool(c_fmw_rel_max_list):
            self._lib.CAENHV_Free(cast(c_fmw_rel_max_list, c_void_p))

        return crate_map

    def get_ch_param(self, slot, channel, param_name, param_type='float'):
        # Prepare inputs for a single channel
        c_slot = c_ushort(slot)
        c_par_name = c_char_p(param_name.encode('utf-8'))
        c_ch_num = c_ushort(1)
        ch_list = (c_ushort * 1)(channel)

        # Create the appropriate array based on parameter type
        if param_type == 'float':
            val_array = (c_float * 1)()
        else:
            val_array = (c_int * 1)()

        result = self._lib.CAENHV_GetChParam(
            self.handle.value, c_slot, c_par_name, c_ch_num, ch_list, val_array
        )

        if result == 0:
            return val_array[0]
        else:
            raise Exception(
                f"Failed to get {param_name} on slot {slot} ch {channel}: {self.get_error()}")

    def set_ch_param(self, slot, channel, param_name, value, param_type='float'):
        # Prepare inputs for a single channel
        c_slot = c_ushort(slot)
        c_par_name = c_char_p(param_name.encode('utf-8'))
        c_ch_num = c_ushort(1)
        ch_list = (c_ushort * 1)(channel)

        # Create and populate the appropriate array based on parameter type
        if param_type == 'float':
            val_array = (c_float * 1)(value)
        elif param_type == 'string':
            val_array = ctypes.create_string_buffer(value.encode('utf-8'))
        else:
            val_array = (c_int * 1)(value)

        result = self._lib.CAENHV_SetChParam(
            self.handle.value, c_slot, c_par_name, c_ch_num, ch_list, val_array
        )

        if result != 0:
            raise Exception(
                f"Failed to set {param_name} on slot {slot} ch {channel}: {self.get_error()}")

    def __enter__(self):
        # Support for 'with' statement
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Automatically disconnect when exiting 'with' block
        if self.is_connected:
            self.deinit_system()

    # ==========================================
    # User-Friendly Helper Methods
    # ==========================================

    def get_vmon(self, slot, channel):
        # Read Monitored Voltage (VMon)
        return self.get_ch_param(slot, channel, "VMon", param_type='float')

    def get_imon(self, slot, channel):
        # Read Monitored Current (IMon)
        return self.get_ch_param(slot, channel, "IMon", param_type='float')

    def set_vset(self, slot, channel, value):
        # Set Target Voltage (V0Set)
        self.set_ch_param(slot, channel, "V0Set", value, param_type='float')

    def set_iset(self, slot, channel, value):
        # Set Current Limit (I0Set)
        self.set_ch_param(slot, channel, "I0Set", value, param_type='float')

    def turn_on(self, slot, channel):
        # Power On Channel (Pw = 1)
        self.set_ch_param(slot, channel, "Pw", 1, param_type='int')

    def turn_off(self, slot, channel):
        # Power Off Channel (Pw = 0)
        self.set_ch_param(slot, channel, "Pw", 0, param_type='int')

    def set_name(self, slot, channel, name):
        # Set Channel Name
        # Note: Some boards do not fully support the Name parameter.
        try:
            self.set_ch_param(slot, channel, "Name", name, param_type='string')
        except Exception as e:
            err_str = str(e).lower()
            if "system configuration" in err_str or "not supported" in err_str or err_str.endswith(": ok"):
                return  # Hardware limitation; skip silently
            import logging
            logging.warning(f"Ignored non-critical error while setting Name: {e}")

    def get_status(self, slot, channel):
        # Get Channel Status (Status is returned as an integer bitmask)
        return self.get_ch_param(slot, channel, "Status", param_type='int')
