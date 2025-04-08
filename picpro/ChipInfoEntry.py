import dataclasses
import functools
from picpro.ProgrammingVariables import ProgrammingVariables
from picpro.exceptions import FuseError
from picpro.tools import indexwise_and


@dataclasses.dataclass
class ChipInfoEntry:
    """A single entry from a chipinfo file, with methods for feeding data to protocol_interface."""

    chip_name: str
    include: bool
    socket_image: str
    erase_mode: int
    flash_chip: bool
    power_sequence: str
    program_delay: int
    program_tries: int
    over_program: int
    core_type: str
    rom_size: int
    eeprom_size: int
    fuse_blank: list
    cp_warn: bool
    cal_word: bool
    band_gap: bool
    icsp_only: bool
    chip_id: int
    fuses: dict

    _core_type_dict = {
        'bit16_a': 1,
        'bit16_b': 2,
        'bit14_g': 3,
        'bit12_a': 4,
        'bit14_a': 5,
        'bit14_b': 6,
        'bit14_c': 7,
        'bit14_d': 8,
        'bit14_e': 9,
        'bit14_f': 10,
        'bit12_b': 11,
        'bit14_h': 12,
        'bit16_c': 13,
        'newf12b': None  # !FIXME Not in docs
    }

    _power_sequence_dict = {
        'Vcc': 0,
        'VccVpp1': 1,
        'VccVpp2': 2,
        'Vpp1Vcc': 3,
        'Vpp2Vcc': 4,
        'VccFastVpp1': 1,
        'VccFastVpp2': 2
    }

    _vcc_vpp_delay_dict = {
        'Vcc': False,
        'VccVpp1': False,
        'VccVpp2': False,
        'Vpp1Vcc': False,
        'Vpp2Vcc': False,
        'VccFastVpp1': True,
        'VccFastVpp2': True
    }

    _socket_image_dict = {
        '8pin': 'socket pin 13',
        '14pin': 'socket pin 13',
        '18pin': 'socket pin 2',
        '28Npin': 'socket pin 1',
        '40pin': 'socket pin 1'
    }

    def to_dict(self) -> dict:
        return {
            'chip_name': self.chip_name,
            'include': self.include,
            'socket_image': self.socket_image,
            'erase_mode': self.erase_mode,
            'flash_chip': self.flash_chip,
            'power_sequence': self.power_sequence,
            'program_delay': self.program_delay,
            'program_tries': self.program_tries,
            'over_program': self.over_program,
            'core_type': self.core_type,
            'rom_size': self.rom_size,
            'eeprom_size': self.eeprom_size,
            'fuse_blank': self.fuse_blank,
            'cp_warn': self.cp_warn,
            'cal_word': self.cal_word,
            'band_gap': self.band_gap,
            'icsp_only': self.icsp_only,
            'chip_id': self.chip_id,
            'fuses': self.fuses
        }

    @functools.cached_property
    def programming_vars(self) -> ProgrammingVariables:
        """Returns a ProgrammingVars"""

        core_type_int = self._core_type_dict.get(self.core_type)
        if not core_type_int:
            raise ValueError('Failed to identify core_type.')

        return ProgrammingVariables(
            rom_size=self.rom_size,
            eeprom_size=self.eeprom_size,
            core_type=core_type_int,
            flag_calibration_value_in_rom=self.cal_word,
            flag_band_gap_fuse=self.band_gap,
            # T.Nixon says this is the rule for this flag.
            flag_18f_single_panel_access_mode=self.core_type == 'bit16_a',
            flag_vcc_vpp_delay=self._vcc_vpp_delay_dict[self.power_sequence],
            program_delay=self.program_delay,
            power_sequence=self._power_sequence_dict[self.power_sequence],
            erase_mode=self.erase_mode,
            program_retries=self.program_tries,
            over_program=self.over_program,
            fuse_blank=self.fuse_blank,
        )

    @functools.cached_property
    def core_bits(self) -> int:

        if self.core_type in ['bit16_a', 'bit16_b', 'bit16_c']:
            return 16
        if self.core_type in ['bit14_a', 'bit14_b', 'bit14_c', 'bit14_d', 'bit14_e', 'bit14_f', 'bit14_g', 'bit14_h']:
            return 14
        if self.core_type in ['bit12_a', 'bit12_b']:
            return 12

        raise ValueError('Failed to detect core bits.')

    def decode_fuse_data(self, fuse_values: list) -> dict:
        """Given a list of fuse values, return a dict of symbolic
        (fuse : value) mapping representing the fuses that are set."""

        fuse_param_list = self.fuses
        result = {}

        for fuse_param in fuse_param_list:
            fuse_settings = fuse_param_list[fuse_param]

            # Try to determine which of the settings for this fuse is
            # active.
            # Fuse setting is active if ((fuse_value & setting) ==
            # (fuse_value))
            # We need to check all fuse values to find the best one.
            # The best is the one which clears the most bits and still
            # matches.  So we start with a best_value of 0xffff (no
            # bits cleared.)
            best_value = [0xffff] * len(fuse_values)
            fuse_identified = False
            for setting in fuse_settings:
                setting_value = fuse_settings[setting]

                if indexwise_and(fuse_values, setting_value) == fuse_values:
                    # If this setting value clears more bits than
                    # best_value, it's our new best value.
                    if indexwise_and(best_value, setting_value) != best_value:
                        best_value = indexwise_and(best_value, setting_value)
                        result[fuse_param] = setting
                        fuse_identified = True
            if not fuse_identified:
                raise FuseError('Could not identify fuse setting.')

        return result

    def encode_fuse_data(self, fuse_dict: dict) -> list:
        result = list(self.fuse_blank)
        fuse_param_list = self.fuses
        for fuse in fuse_dict:
            fuse_value = fuse_dict[fuse]

            if fuse not in fuse_param_list:
                raise FuseError('Unknown fuse "{}".'.format(fuse))
            fuse_settings = fuse_param_list[fuse]

            if fuse_value not in fuse_settings:
                raise FuseError('Invalid fuse setting: "{}" = "{}"'.format(fuse, fuse_value))

            result = indexwise_and(result, fuse_settings[fuse_value])

        return result

    @property
    def has_eeprom(self) -> bool:
        return self.eeprom_size != 0

    @property
    def pin1_location_text(self) -> str:
        return self._socket_image_dict[self.socket_image]

    @property
    def fuse_doc(self) -> str:
        result = ''
        fuse_param_list = self.fuses
        for fuse in fuse_param_list:
            fuse_settings = fuse_param_list[fuse]

            result = result + '\'' + fuse + '\' : ('
            first = True
            for setting in fuse_settings:
                if not first:
                    result = result + ', '
                result = result + '\'' + setting + '\''
                first = False
            result = result + ')\n'
        return result
