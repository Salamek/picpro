import re

from pic_k150_programmer.ChipInfoEntry import ChipInfoEntry
from pic_k150_programmer.exceptions import FormatError
from pic_k150_programmer.tools import hex_int


class ChipInfoReader:
    # Class for reading chipinfo files, which provide information about different types of PICs.
    boolean_dict = {
        'y': True,
        '1': True,
        'n': False,
        '0': False
    }

    def __init__(self, file_name='', file=None):
        if not file:
            file = open(file_name, 'U')

        def handle_hex(xstr):
            return hex_int(xstr, 16)

        def handle_int(xstr):
            return int(xstr, 10)

        def handle_bool(xstr):
            return self.boolean_dict[xstr]

        def handle_core_type(xstr):
            return ChipInfoEntry.core_type_dict[xstr]

        special_handlers = {
            'BandGap': handle_bool,
            'CALword': handle_bool,
            'ChipID': handle_hex,
            'CoreType': handle_core_type,
            'CPwarn': handle_bool,
            'EEPROMsize': handle_hex,
            'EraseMode': handle_int,
            'FlashChip': handle_bool,
            'FUSEblank': (lambda xstr: map(lambda x: hex_int(x, 16), xstr.split(' '))),
            'ICSPonly': handle_bool,
            'OverProgram': handle_int,
            'ProgramDelay': handle_int,
            'ProgramTries': handle_int,
            'ROMsize': handle_hex,
        }

        assignment_regexp = re.compile(r'^(\w+)\s*=\s*(.*)\s*$')
        fuse_value_regexp_str = r'"([^"]*)"\s*=\s*([0-9a-fA-F]+(?:&[0-9a-fA-F]+)*)'
        fuse_value_regexp = re.compile(fuse_value_regexp_str)
        fuse_list_regexp = re.compile(r'^LIST\d+\s+FUSE(?P<fuse>\d)\s+"(?P<name>[^"]*)"\s*(?P<values>.*)$')
        non_blank_regexp = re.compile(r'.*\S.*$')
        self.chip_entries = {}
        entry = None
        line_number = 0
        for line in file:
            line_number += 1
            match = assignment_regexp.match(line)
            if match:
                lhs, rhs = match.groups()

                # if lhs is 'CHIPname', this is the start of a new section.
                if lhs == 'CHIPname':
                    chip_name = rhs.lower()
                    self.chip_entries[chip_name] = entry
                    entry = {
                        'CHIPname': chip_name
                    }
                else:
                    # General case.  CHIPname must be valid.
                    try:
                        if lhs in special_handlers:
                            entry[lhs] = special_handlers[lhs](rhs.lower())
                        else:
                            entry[lhs] = rhs
                    except NameError:
                        # Some extraneous line in the file...  do we care?
                        raise FormatError('Assignment outside of chip definition @{}: {}'.format(line_number, line))
            else:
                match = fuse_list_regexp.match(line)
                if match:
                    fuse, name, values_string = match.groups()

                    fuses = entry.setdefault('fuses', {})
                    fuses.setdefault(name, {})

                    values = fuse_value_regexp.findall(values_string)
                    for value_pair in values:
                        (lhs, rhs) = value_pair
                        # rhs may have multiple fuse values, in the form
                        #   xxxx&xxxx&xxxx...
                        # This means that each xxxx applies to the next
                        # consecutive fuse.
                        fuse_values = list(map(lambda xstr: hex_int(xstr, 16), rhs.split('&')))
                        fuse_number = int(fuse)
                        fuses[name][lhs] = zip(range(fuse_number - 1, (fuse_number + len(fuse_values) - 1)), fuse_values)
                elif non_blank_regexp.match(line):
                    raise FormatError('Unrecognized line format {}'.format(line))

    def get_chip(self, name):
        return ChipInfoEntry(**self.chip_entries[name.lower()])
