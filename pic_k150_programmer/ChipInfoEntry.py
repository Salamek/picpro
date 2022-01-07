from typing import Union
from pic_k150_programmer.IChipInfoEntry import IChipInfoEntry
from pic_k150_programmer.ProgrammingVars import ProgrammingVars
from pic_k150_programmer.exceptions import FuseError
from pic_k150_programmer.tools import indexwise_and


class ChipInfoEntry(IChipInfoEntry):
    """A single entry from a chipinfo file, with methods for feeding data to protocol_interface."""

    core_type_dict = {
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

    power_sequence_dict = {
        'Vcc': 0,
        'VccVpp1': 1,
        'VccVpp2': 2,
        'Vpp1Vcc': 3,
        'Vpp2Vcc': 4,
        'VccFastVpp1': 1,
        'VccFastVpp2': 2
    }

    vcc_vpp_delay_dict = {
        'Vcc': False,
        'VccVpp1': False,
        'VccVpp2': False,
        'Vpp1Vcc': False,
        'Vpp2Vcc': False,
        'VccFastVpp1': True,
        'VccFastVpp2': True
    }

    socket_image_dict = {
        '8pin': 'socket pin 13',
        '14pin': 'socket pin 13',
        '18pin': 'socket pin 2',
        '28Npin': 'socket pin 1',
        '40pin': 'socket pin 1'
    }

    def __init__(self,
                 chip_name: str, include: bool, socket_image: str, erase_mode: int,
                 flash_chip: bool, power_sequence: str, program_delay: int, program_tries: int,
                 over_program: int, core_type: int, rom_size: int, eeprom_size: int,
                 fuse_blank: list, cp_warn: bool, cal_word: bool, band_gap: bool, icsp_only: bool,
                 chip_id: int, fuses: dict):

        self.vars = {
            'CHIPname': chip_name,
            'INCLUDE': include,
            'SocketImage': socket_image,
            'erase_mode': erase_mode,
            'FlashChip': flash_chip,
            'power_sequence': self.power_sequence_dict[power_sequence],
            'power_sequence_str': power_sequence,
            'program_delay': program_delay,
            'program_tries': program_tries,
            'over_program': over_program,
            'core_type': core_type,
            'rom_size': rom_size,
            'eeprom_size': eeprom_size,
            'FUSEblank': fuse_blank,
            'CPwarn': cp_warn,
            'flag_calibration_value_in_rom': cal_word,
            'flag_band_gap_fuse': band_gap,
            'ICSPonly': icsp_only,
            'ChipID': chip_id,
            'fuses': fuses
        }

    @property
    def programming_vars(self) -> ProgrammingVars:
        """Returns a ProgrammingVars"""
        return ProgrammingVars(
            rom_size=self.vars['rom_size'],
            eeprom_size=self.vars['eeprom_size'],
            core_type=self.vars['core_type'],
            flag_calibration_value_in_rom=self.vars['flag_calibration_value_in_rom'],
            flag_band_gap_fuse=self.vars['flag_band_gap_fuse'],
            # T.Nixon says this is the rule for this flag.
            flag_18f_single_panel_access_mode=(self.vars['core_type'] == self.core_type_dict['bit16_a']),
            flag_vcc_vpp_delay=self.vcc_vpp_delay_dict[self.vars['power_sequence_str']],
            program_delay=self.vars['program_delay'],
            power_sequence=self.vars['power_sequence'],
            erase_mode=self.vars['erase_mode'],
            program_retries=self.vars['program_tries'],
            over_program=self.vars['over_program']
        )

    def get_core_bits(self) -> Union[int, None]:
        core_type = self.vars['core_type']

        if core_type in [1, 2]:
            return 16
        elif core_type in [3, 5, 6, 7, 8, 9, 10]:
            return 14
        elif core_type in [4]:
            return 12
        else:
            return None

    def decode_fuse_data(self, fuse_values: list) -> dict:
        """Given a list of fuse values, return a dict of symbolic
        (fuse : value) mapping representing the fuses that are set."""

        fuse_param_list = self.vars['fuses']
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
        result = list(self.vars['FUSEblank'])
        fuse_param_list = self.vars['fuses']
        for fuse in fuse_dict:
            fuse_value = fuse_dict[fuse]

            if fuse not in fuse_param_list:
                raise FuseError('Unknown fuse "{}".'.format(fuse))
            fuse_settings = fuse_param_list[fuse]

            if fuse_value not in fuse_settings:
                raise FuseError('Invalid fuse setting: "{}" = "{}"'.format(fuse, fuse_value))

            result = indexwise_and(result, fuse_settings[fuse_value])

        return result

    def has_eeprom(self) -> bool:
        return self.vars['eeprom_size'] != 0

    def pin1_location_text(self) -> str:
        return self.socket_image_dict[self.vars['SocketImage']]

    def fuse_doc(self) -> str:
        result = ''
        fuse_param_list = self.vars['fuses']
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
