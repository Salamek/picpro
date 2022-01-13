import re
from typing import Union
from picpro.ChipInfoEntry import ChipInfoEntry
from picpro.exceptions import FormatError


class ChipInfoReader:
    # Class for reading chipinfo files, which provide information about different types of PICs.
    boolean_dict = {
        'y': True,
        '1': True,
        'n': False,
        '0': False
    }

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
        def handle_hex(xstr: str) -> int:
            return int(xstr, 16)

        def handle_int(xstr: str) -> int:
            return int(xstr, 10)

        def handle_bool(xstr: str) -> Union[bool, None]:
            return self.boolean_dict.get(xstr)

        def handle_core_type(xstr: str) -> Union[int, None]:
            return ChipInfoEntry.core_type_dict.get(xstr)

        special_handlers = {
            'band_gap': handle_bool,
            'cal_word': handle_bool,
            'chip_id': handle_hex,
            'core_type': handle_core_type,
            'cp_warn': handle_bool,
            'eeprom_size': handle_hex,
            'erase_mode': handle_int,
            'flash_chip': handle_bool,
            'fuse_blank': lambda xstr: map(lambda x: int(x, 16), xstr.split(' ')),
            'icsp_only': handle_bool,
            'over_program': handle_int,
            'program_delay': handle_int,
            'program_tries': handle_int,
            'rom_size': handle_hex,
            'include': handle_bool
        }

        assignment_regexp = re.compile(r'^(\S+)\s*=\s*(.*)\s*$')
        fuse_value_regexp_str = r'"([^"]*)"\s*=\s*([0-9a-fA-F]+(?:&[0-9a-fA-F]+)*)'
        fuse_value_regexp = re.compile(fuse_value_regexp_str)
        fuse_list_regexp = re.compile(r'^LIST\d+\s+FUSE(?P<fuse>\d)\s+"(?P<name>[^"]*)"\s*(?P<values>.*)$')
        non_blank_regexp = re.compile(r'.*\S.*$')
        self.chip_entries = {}
        line_number = 0
        with open(file_name, 'r', encoding='UTF-8') as file:
            for line in file:
                line_number += 1
                match = assignment_regexp.match(line)
                if match:
                    lhs_raw, rhs = match.groups()
                    lhs = self.chip_info_key_replacements.get(lhs_raw)
                    if lhs is None:
                        raise FormatError('Key replacement is None for {}'.format(lhs_raw))
                    # if lhs is 'chip_name', this is the start of a new section.
                    if lhs == 'chip_name':
                        chip_name = rhs.lower()
                        entry = {
                            'chip_name': chip_name
                        }
                        self.chip_entries[chip_name] = entry
                    else:
                        # General case. CHIPname must be valid.
                        try:
                            special_handler = special_handlers.get(lhs)
                            if special_handler:
                                resolved_value = special_handler(rhs.lower())
                                entry[lhs] = resolved_value
                            else:
                                entry[lhs] = rhs
                        except NameError as e:
                            # Some extraneous line in the file...  do we care?
                            raise FormatError('Assignment outside of chip definition @{}: {}'.format(line_number, line)) from e
                else:
                    match = fuse_list_regexp.match(line)
                    if match:
                        fuse, name, values_string = match.groups()

                        fuses = entry.setdefault('fuses', {})
                        fuses.setdefault(name, {})

                        values = fuse_value_regexp.findall(values_string)
                        for value_pair in values:
                            lhs, rhs = value_pair
                            # rhs may have multiple fuse values, in the form
                            #   xxxx&xxxx&xxxx...
                            # This means that each xxxx applies to the next
                            # consecutive fuse.
                            fuse_values = list(map(lambda xstr: int(xstr, 16), rhs.split('&')))
                            fuse_number = int(fuse)
                            fuses[name][lhs] = zip(range(fuse_number - 1, (fuse_number + len(fuse_values) - 1)), fuse_values)
                    elif non_blank_regexp.match(line):
                        raise FormatError('Unrecognized line format {}'.format(line))

    def get_chip(self, name: str) -> ChipInfoEntry:
        chip_entry = self.chip_entries[name.lower()]

        # @TODO We don't know what these are doing?!
        # Remove for now...
        del chip_entry['program_flag_2']
        del chip_entry['panel_sizing']

        # These are ignored in new file format
        chip_entry['program_tries'] = chip_entry.get('program_tries', 1)
        chip_entry['over_program'] = chip_entry.get('over_program', 0)

        return ChipInfoEntry(**chip_entry)
