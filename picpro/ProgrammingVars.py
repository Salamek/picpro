from typing import List


class ProgrammingVars:
    def __init__(self, rom_size: int,
                 eeprom_size: int,
                 core_type: int,
                 flag_calibration_value_in_rom: bool,
                 flag_band_gap_fuse: bool,
                 flag_18f_single_panel_access_mode: bool,
                 flag_vcc_vpp_delay: bool,
                 program_delay: int,
                 power_sequence: int,
                 erase_mode: int,
                 program_retries: int,
                 over_program: int,
                 fuse_blank: List[int]
                 ):
        self.rom_size = rom_size
        self.eeprom_size = eeprom_size
        self.core_type = core_type
        self.flag_calibration_value_in_rom = flag_calibration_value_in_rom
        self.flag_band_gap_fuse = flag_band_gap_fuse
        self.flag_18f_single_panel_access_mode = flag_18f_single_panel_access_mode
        self.flag_vcc_vpp_delay = flag_vcc_vpp_delay
        self.program_delay = program_delay
        self.power_sequence = power_sequence
        self.erase_mode = erase_mode
        self.program_retries = program_retries
        self.over_program = over_program
        self.fuse_blank = fuse_blank
