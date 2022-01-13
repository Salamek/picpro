import re
import logging
from typing import Union, List, Dict
from picpro.ChipInfoEntry import ChipInfoEntry
from picpro.exceptions import FormatError


def handle_hex(input_str: str) -> int:
    return int(input_str, 16)


def handle_int(input_str: str) -> int:
    return int(input_str, 10)


def handle_core_type(input_str: str) -> Union[int, None]:
    return ChipInfoEntry.core_type_dict.get(input_str)


def handle_fuse_blank(input_str: str) -> List[int]:
    return [int(x, 16) for x in input_str.strip().split(' ')]


def handle_lower(input_str: str) -> str:
    return input_str.lower()


def handle_bool(input_str: str) -> Union[bool, None]:
    boolean_dict = {
        'y': True,
        '1': True,
        'n': False,
        '0': False
    }
    return boolean_dict.get(input_str)


class ChipInfoReader:
    chip_entries: Dict[str, ChipInfoEntry] = {}
    assignment_regexp = re.compile(r'^(\S+)\s*=\s*(.*)\s*$')
    fuse_value_regexp = re.compile(r'"([^"]*)"\s*=\s*([0-9a-fA-F]+(?:&[0-9a-fA-F]+)*)')
    fuse_list_regexp = re.compile(r'^LIST\d+\s+FUSE(?P<fuse>\d)\s+"(?P<name>[^"]*)"\s*(?P<values>.*)$')
    non_blank_regexp = re.compile(r'.*\S.*$')

    # Class for reading chipinfo files, which provide information about different types of PICs.

    chip_info_key_replacements = {
        'CHIPname': 'chip_name',
        'BandGap': 'band_gap',
        'INCLUDE': 'include',
        'SocketImage': 'socket_image',
        'KITSRUS.COM': 'socket_image',
        'PowerSequence': 'power_sequence',
        'CALword': 'cal_word',
        'ChipID': 'chip_id',
        'CoreType': 'core_type',
        'CPwarn': 'cp_warn',
        'EEPROMsize': 'eeprom_size',
        'EraseMode': 'erase_mode',
        'FlashChip': 'flash_chip',
        'FUSEblank': 'fuse_blank',
        'ICSPonly': 'icsp_only',
        'OverProgram': 'over_program',
        'ProgramDelay': 'program_delay',
        'ProgramTries': 'program_tries',
        'ROMsize': 'rom_size',
        'ProgramFlag2': 'program_flag_2',
        'PanelSizing': 'panel_sizing'
    }

    def __init__(self, file_name: str):
        self.special_handlers = {
            'chip_name': handle_lower,
            'band_gap': handle_bool,
            'cal_word': handle_bool,
            'chip_id': handle_hex,
            'core_type': handle_core_type,
            'cp_warn': handle_bool,
            'eeprom_size': handle_hex,
            'erase_mode': handle_int,
            'flash_chip': handle_bool,
            'fuse_blank': handle_fuse_blank,
            'icsp_only': handle_bool,
            'over_program': handle_int,
            'program_delay': handle_int,
            'program_tries': handle_int,
            'rom_size': handle_hex,
            'include': handle_bool
        }

        # Open file and split it into data blocks, so we can process data in blocks
        with open(file_name, 'r', encoding='UTF-8') as file:
            block: Union[None, dict] = None
            lines = file.readlines()
            number_of_lines = len(lines)
            for line_index, line in enumerate(lines):
                line_number = line_index + 1
                try:
                    stripped_line = line.strip()
                    if stripped_line:
                        # We have line, add to current block
                        if not block:
                            block = {
                                'fuses': {}
                            }
                        self.parse_line(block, stripped_line, line_number)
                    if block and (not stripped_line or line_number == number_of_lines):
                        # Empty line or end of file means end of block
                        # @TODO We don't know what these are doing?!
                        del block['program_flag_2']
                        del block['panel_sizing']

                        # These are ignored in new file format
                        block['program_tries'] = block.get('program_tries', 1)
                        block['over_program'] = block.get('over_program', 0)
                        self.chip_entries[block['chip_name']] = ChipInfoEntry(**block)
                        block = None
                except FormatError as e:
                    # Destroy this block
                    block = None
                    logging.error('Parsing of line %s failed, ignoring whole block...', line_number, exc_info=e)

    def parse_line(self, block: dict, line: str, line_number: int) -> None:
        match_assignment_regexp = self.assignment_regexp.match(line)
        if match_assignment_regexp:
            lhs_raw, rhs = match_assignment_regexp.groups()
            lhs = self.chip_info_key_replacements.get(lhs_raw)
            if lhs is None:
                raise FormatError('Key replacement is None for {}'.format(lhs_raw))
            try:
                found_special_handler = self.special_handlers.get(lhs)
                if found_special_handler:
                    special_handler = found_special_handler
                    block[lhs] = special_handler(rhs.lower())
                else:
                    block[lhs] = rhs
            except NameError as e:
                # Some extraneous line in the file...  do we care?
                raise FormatError('Assignment outside of chip definition @{}: {}'.format(line_number, line)) from e

        else:
            match_fuse_list_regexp = self.fuse_list_regexp.match(line)
            if match_fuse_list_regexp:
                fuse, name, values_string = match_fuse_list_regexp.groups()

                fuses = {}
                values = self.fuse_value_regexp.findall(values_string)
                for value_pair in values:
                    lhs, rhs = value_pair
                    # rhs may have multiple fuse values, in the form
                    #   xxxx&xxxx&xxxx...
                    # This means that each xxxx applies to the next
                    # consecutive fuse.
                    fuse_values = [int(xstr, 16) for xstr in rhs.split('&')]
                    fuse_number = int(fuse)

                    fuses[lhs] = list(zip(range(fuse_number - 1, (fuse_number + len(fuse_values) - 1)), fuse_values))

                block['fuses'][name] = fuses
            elif self.non_blank_regexp.match(line):
                raise FormatError('Unrecognized line format {}'.format(line))

    def get_chip(self, name: str) -> ChipInfoEntry:
        return self.chip_entries[name.lower()]
