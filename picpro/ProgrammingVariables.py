import dataclasses
import struct


@dataclasses.dataclass
class ProgrammingVariablesFlags:
    flag_calibration_value_in_rom: bool
    flag_band_gap_fuse: bool
    flag_18f_single_panel_access_mode: bool
    flag_vcc_vpp_delay: bool

    @classmethod
    def from_int(cls, flags: int) -> 'ProgrammingVariablesFlags':
        return cls(
            flag_calibration_value_in_rom = bool(flags & 1),
            flag_band_gap_fuse= bool(flags & 2),
            flag_18f_single_panel_access_mode= bool(flags & 4),
            flag_vcc_vpp_delay= bool(flags & 8),
        )


    def to_int(self) -> int:
        return (
                (self.flag_calibration_value_in_rom and 1) |
                (self.flag_band_gap_fuse and 2) |
                (self.flag_18f_single_panel_access_mode and 4) |
                (self.flag_vcc_vpp_delay and 8)
        )


@dataclasses.dataclass
class ProgrammingVariables:
    rom_size_words: int
    eeprom_size: int
    core_type: int
    flags: ProgrammingVariablesFlags
    program_delay: int
    power_sequence: int
    erase_mode: int
    program_retries: int
    over_program: int

    @classmethod
    def from_bytes(cls, data: bytes) -> 'ProgrammingVariables':
        (
            rom_size_words,
            eeprom_size,
            core_type,
            flags,
            program_delay,
            power_sequence,
            erase_mode,
            program_retries,
            over_program,
        ) = struct.unpack('>HHBBBBBBB', data)

        if not rom_size_words:
            msg = 'rom_size_words cannot be empty'
            raise ValueError(msg)

        if rom_size_words % 32 != 0:
            msg = 'rom_size_words has to be multiple of 32'
            raise ValueError(msg)

        if eeprom_size and eeprom_size % 32 != 0:
            msg = 'eeprom_size has to be multiple of 32'
            raise ValueError(msg)

        if core_type not in range(1, 14):  # note: 13 is max
            msg = 'Unknown core_type'
            raise ValueError(msg)

        if power_sequence not in range(5):  # note: 13 is max
            msg = 'Unknown power_sequence'
            raise ValueError(msg)

        if not program_retries:
            msg = 'program_retries has to be at least 1'
            raise ValueError(msg)

        return cls(
            rom_size_words=rom_size_words,
            eeprom_size=eeprom_size,
            core_type=core_type,
            flags=ProgrammingVariablesFlags.from_int(flags),
            program_delay=program_delay,
            power_sequence=power_sequence,
            erase_mode=erase_mode,
            program_retries=program_retries,
            over_program=over_program,
        )

    def to_bytes(self) -> bytes:
        return struct.pack(
            '>HHBBBBBBB',
            self.rom_size_words,
            self.eeprom_size,
            self.core_type,
            self.flags.to_int(),
            self.program_delay,
            self.power_sequence,
            self.erase_mode,
            self.program_retries,
            self.over_program,
        )
