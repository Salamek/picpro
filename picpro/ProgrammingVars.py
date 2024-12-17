import dataclasses
from typing import List


@dataclasses.dataclass
class ProgrammingVars:
    rom_size: int
    eeprom_size: int
    core_type: int
    flag_calibration_value_in_rom: bool
    flag_band_gap_fuse: bool
    flag_18f_single_panel_access_mode: bool
    flag_vcc_vpp_delay: bool
    program_delay: int
    power_sequence: int
    erase_mode: int
    program_retries: int
    over_program: int
    fuse_blank: List[int]
