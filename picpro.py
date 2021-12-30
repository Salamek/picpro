#!/usr/bin/python
"""The picpro module provides a simple program-level and command-line-level interface to the PIC programmers made by kitsrus.com.

This module is released under the GPL by its author.
This work would not have been possible without the programming protocol documentation kindly provided by kitsrus as well as the assistance of people at kitsrus.com and in the community.
Send comments or bug reports related to this module to tetsujin@users.sf.net
"""

# There should never be a problem with the standard imports.  But...
try:
    import getopt
    import os.path
    import re
    import struct
    import sys
    import time
except ImportError:
    print ("Failed to import standard Python libraries.  Please make sure your Python installation is complete and up-to-date.")
    sys.exit(1)


try:
    import serial
except ImportError:
    print ("Unable to find Python Serial library.  Please download and install the serial library from http://www.sf.net/projects/pyserial")
    sys.exit(1)

import data_string
import hex_file_reader

module_location = os.path.dirname(os.path.realpath(__file__)) + os.sep


def print_usage_and_abort():
    print (handle_command_line.__doc__)
    sys.exit(1)


def handle_command_line(cmd_args):
    # @TODO Rewrite this shit
    """micropro: program a PIC using the Kits R Us serial/USB PIC programmer.

Arguments:
    "-p x" (or "--port=x"): use serial port x
    "--pic_type=x": specify type of PIC to be programmed (use '16F84A',
                  not 'PIC16F84A')
    "-i file.hex" (or "--input=file.hex"): specify name of HEX file to use
    "--fuse=fuse_name:value": (optional) specify a value for a programming flag
    "--ID=PIC_id": (optional) specify ID to be programmed to PIC.
    "--program": (default) Program the PIC
    "--verify": Verify only, do not program
    "-h" (or "--help"): display this message"""

    try:
        opts, args = getopt.getopt(cmd_args[1:], 'p:i:h',
                                     ['port=', 'pic_type=', 'input=',
                                      'fuse=', 'ID=', 'help',
                                      'icsp', 'program', 'verify'])

        if not args:
            print_usage_and_abort()

        handle_parsed_command_line(opts)
    except getopt.GetoptError:
        print_usage_and_abort()



def handle_parsed_command_line(opts):
    fuses = {}
    ID = None
    program_flag = False
    verify_flag = False
    icsp_mode = False
    for (opt, value) in opts:
        try:
            if (opt == '-h') or (opt == '--help'):
                print_usage_and_abort()
            elif (opt == '-p') or (opt == '--port'):
                port = value
            elif (opt == '-i') or (opt == '--input'):
                hex_file_name = value
            elif opt == '--pic_type':
                pic_type = value
            elif opt == '--fuse':
                split = value.split(':')
                fuses[split[0]] = split[1]
            elif opt == '--ID':
                ID = value
            elif opt == '--verify':
                verify_flag = True
            elif opt == '--program':
                program_flag = True
            elif opt == '--icsp':
                icsp_mode = True
            else:
                print ('Error: Unrecognized option "{}".'.format(opt))
                sys.exit(1)
        except SystemExit:
            raise
        except:
            print ('Error: Invalid usage of option "{}".'.format(opt))
            print_usage_and_abort()

    program = (program_flag or not verify_flag)

    # So let's do this thing...
    try:
        program_pic_args = dict(port=port,
                                pic_type=pic_type,
                                hex_file_name=hex_file_name,
                                fuses=fuses,
                                ID=ID,
                                icsp_mode=icsp_mode)
    except NameError:
        print('Error: Missing required arguments')
        print_usage_and_abort()

    program_pic(port, pic_type, hex_file_name, program, fuses=fuses, ID=ID, icsp_mode=icsp_mode)


class hex_int(int):
    # @TODO WTH?
    """Behaves just like an integer, except its __repr__ in python yields a hex string."""
    #self._method_wrap('__xor__')
    #self._method_wrap('__rshift__')

    def __init__(self, value, radix = 16):
        int.__init__(self, value, radix)

    def __repr__(self):
        if (self >= 0):
            return hex(self)
        else:
            # Avoid "future" warning and ensure eval(repr(self)) == self
            return '-' + hex(-self)

    def maybe_hex_int(value):
        if (isinstance(value, int)):
            return hex_int(value)
        else:
            return value
    maybe_hex_int = staticmethod(maybe_hex_int)


    _method_wrap = lambda super_method_name: lambda *args, **argd: hex_int.maybe_hex_int(int.__dict__[super_method_name](*args, **argd))

    __abs__ = _method_wrap('__abs__')
    __add__ = _method_wrap('__add__')
    __and__ = _method_wrap('__and__')
    __floordiv__ = _method_wrap('__floordiv__')
    __invert__ = _method_wrap('__invert__')
    __lshift__ = _method_wrap('__lshift__')
    __mod__ = _method_wrap('__mod__')
    __mul__ = _method_wrap('__mul__')
    __neg__ = _method_wrap('__neg__')
    __or__ = _method_wrap('__or__')
    __pos__ = _method_wrap('__pos__')
    __pow__ = _method_wrap('__pow__')
    __sub__ = _method_wrap('__sub__')
    __xor__ = _method_wrap('__xor__')
    __radd__ = _method_wrap('__add__')
    __rand__ = _method_wrap('__and__')
    __rfloordiv__ = _method_wrap('__floordiv__')
    __rmul__ = _method_wrap('__mul__')
    __ror__ = _method_wrap('__or__')
    __rsub__ = _method_wrap('__rsub__')
    __rxor__ = _method_wrap('__xor__')


#---------------------------------------------------


class ChipInfoEntry(object):
    """A single entry from a chipinfo file, with methods for feeding data to protocol_interface."""

    class Fuse_Error(Exception):
        "Indicates an erroneous fuse value."

    power_sequence_dict = {'Vcc' : 0,
                           'VccVpp1' : 1,
                           'VccVpp2' : 2,
                           'Vpp1Vcc' : 3,
                           'Vpp2Vcc' : 4,
                           'VccFastVpp1' : 1,
                           'VccFastVpp2' : 2}
    vcc_vpp_delay_dict = {'Vcc' : False,
                          'VccVpp1' : False,
                          'VccVpp2' : False,
                          'Vpp1Vcc' : False,
                          'Vpp2Vcc' : False,
                          'VccFastVpp1' : True,
                          'VccFastVpp2' : True}
    socket_image_dict = {'8pin' : 'socket pin 13',
                         '14pin' : 'socket pin 13',
                         '18pin' : 'socket pin 2',
                         '28Npin' : 'socket pin 1',
                         '40pin' : 'socket pin 1'}

    def __init__(self,
                 CHIPname, INCLUDE, SocketImage, EraseMode,
                 FlashChip, PowerSequence, ProgramDelay, ProgramTries,
                 OverProgram, CoreType, ROMsize, EEPROMsize,
                 FUSEblank, CPwarn, CALword, BandGap, ICSPonly,
                 ChipID, fuses):
        self.vars = {
            'CHIPname' : CHIPname,
            'INCLUDE' : INCLUDE,
            'SocketImage' : SocketImage,
            'erase_mode' : EraseMode,
            'FlashChip' : FlashChip,
            'power_sequence' : self.power_sequence_dict[PowerSequence],
            'power_sequence_str' : PowerSequence,
            'program_delay' : ProgramDelay,
            'program_tries' : ProgramTries,
            'over_program' : OverProgram,
            'core_type' : CoreType,
            'rom_size' : ROMsize,
            'eeprom_size' : EEPROMsize,
            'FUSEblank' : FUSEblank,
            'CPwarn' : CPwarn,
            'flag_calibration_value_in_ROM' : CALword,
            'flag_band_gap_fuse' : BandGap,
            'ICSPonly' : ICSPonly,
            'ChipID' : ChipID,
            'fuses' : fuses}

    def get_programming_vars(self):
        "Returns a dictionary which can be fed as arguments to Protocol_Interface.init_programming_vars()"
        result = dict(
            rom_size = self.vars['rom_size'],
            eeprom_size = self.vars['eeprom_size'],
            core_type = self.vars['core_type'],
            flag_calibration_value_in_ROM = self.vars['flag_calibration_value_in_ROM'],
            flag_band_gap_fuse = self.vars['flag_band_gap_fuse'],
            # T.Nixon says this is the rule for this flag.
            flag_18f_single_panel_access_mode = (self.vars['core_type'] == Chipinfo_Reader.core_type_dict['bit16_a']),
            flag_vcc_vpp_delay = self.vcc_vpp_delay_dict[self.vars['power_sequence_str']],
            program_delay = self.vars['program_delay'],
            power_sequence = self.vars['power_sequence'],
            erase_mode = self.vars['erase_mode'],
            program_retries = self.vars['program_tries'],
            over_program = self.vars['over_program'])

        return result


    def get_core_bits(self):
        core_type = self.vars['core_type']

        if (core_type in [1, 2]):
            return 16
        elif (core_type in [3, 5, 6, 7, 8, 9, 10]):
            return 14
        elif (core_type in [4]):
            return 12
        else:
            return None

    def decode_fuse_data(self, fuse_values):
        ('Given a list of fuse values, return a dict of symbolic ' +
         '(fuse : value) mapping representing the fuses that are set.')

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

                if (indexwise_and(fuse_values, setting_value) ==
                    fuse_values):
                    # If this setting value clears more bits than
                    # best_value, it's our new best value.
                    if (indexwise_and(best_value, setting_value) !=
                        best_value):
                        best_value = indexwise_and(best_value,
                                                   setting_value)
                        result[fuse_param] = setting
                        fuse_identified = True
            if (not fuse_identified):
                raise self.Fuse_Error, 'Could not identify fuse setting.'

        return result


    def encode_fuse_data(self, fuse_dict):
        result = list(self.vars['FUSEblank'])
        fuse_param_list = self.vars['fuses']
        for fuse in fuse_dict:
            fuse_value = fuse_dict[fuse]

            if (fuse not in fuse_param_list):
                raise self.Fuse_Error, 'Unknown fuse \"' + fuse + '\".'
            fuse_settings = fuse_param_list[fuse]

            if (fuse_value not in fuse_settings):
                raise self.Fuse_Error, ('Invalid fuse setting: "' +
                                        fuse + '" = "' + fuse_value +
                                        '".')

            result = indexwise_and(result, fuse_settings[fuse_value])

        return result


    def has_eeprom(self):
        return (self.vars['eeprom_size'] != 0)

    def pin1_location_text(self):
        return (self.socket_image_dict[self.vars['SocketImage']])

    def fuse_doc(self):
        result = ''
        fuse_param_list = self.vars['fuses']
        for fuse in fuse_param_list:
            fuse_settings = fuse_param_list[fuse]

            result = result + '\'' + fuse + '\' : ('
            first = True
            for setting in fuse_settings:
                if (not first):
                    result = result + ', '
                result = result + '\'' + setting + '\''
                first = False
            result = result + ')\n'
        return result


#-------------------------------------------------


class Chipinfo_Reader(object):
    # Class for reading chipinfo files, which provide information about different types of PICs.
    boolean_dict = {'y' : True,
                    '1' : True,
                    'n' : False,
                    '0' : False}
    core_type_dict = {'bit16_a' : 1,
                      'bit16_b' : 2,
                      'bit14_g' : 3,
                      'bit12_a' : 4,
                      'bit14_a' : 5,
                      'bit14_b' : 6,
                      'bit14_c' : 7,
                      'bit14_d' : 8,
                      'bit14_e' : 9,
                      'bit14_f' : 10,
                      'bit12_b' : 11,
                      'bit14_h' : 12,
                      'bit16_c' : 13}

    class Format_Error(Exception):
        "Indicates an error in the chipinfo file's format."

    def __init__(self, file_name = '', file = None):
        if (file == None):
            file = open(file_name, 'U')

        def handle_hex(xstr):
            return hex_int(xstr, 16)
        def handle_int(xstr):
            return int(xstr, 10)
        def handle_bool(xstr):
            return self.boolean_dict[xstr]
        def handle_core_type(xstr):
            return self.core_type_dict[xstr]

        special_handlers = {
                            'BandGap' : handle_bool,
                            'CALword' : handle_bool,
                            'ChipID' : handle_hex,
                            'CoreType' : handle_core_type,
                            'CPwarn' : handle_bool,
                            'EEPROMsize' : handle_hex,
                            'EraseMode' : handle_int,
                            'FlashChip' : handle_bool,
                            'FUSEblank' :
                            (lambda xstr: map(lambda x: hex_int(x, 16),
                                              xstr.split(' '))),
                            'ICSPonly' : handle_bool,
                            'OverProgram' : handle_int,
                            'ProgramDelay' : handle_int,
                            'ProgramTries' : handle_int,
                            'ROMsize' : handle_hex,
                            }

        assignment_regexp = re.compile(r'^(\w+)\s*=\s*(.*)\s*$')
        fuse_value_regexp_str = r'"([^"]*)"\s*=\s*([0-9a-fA-F]+(?:&[0-9a-fA-F]+)*)'
        fuse_value_regexp = re.compile(fuse_value_regexp_str)
        fuse_list_regexp = re.compile(
            r'^LIST\d+\s+FUSE(?P<fuse>\d)\s+"(?P<name>[^"]*)"\s*(?P<values>.*)$')
        nonblank_regexp = re.compile(r'.*\S.*$')
        self.chip_entries = {}
        CHIPname = ''
        entry = None
        line_number = 0;
        for line in file:
            line_number += 1
            match = assignment_regexp.match(line)
            if (match):
                (lhs, rhs) = match.groups()

                # if lhs is 'CHIPname', this is the start of a new section.
                if (lhs == 'CHIPname'):
                    CHIPname = rhs.lower()
                    entry = {}
                    self.chip_entries[CHIPname] = entry
                    entry['CHIPname'] = CHIPname
                else:
                    # General case.  CHIPname must be valid.
                    try:
                        if (lhs in special_handlers):
                            entry[lhs] = special_handlers[lhs](rhs.lower())
                        else:
                            entry[lhs] = rhs
                    except NameError:
                        # Some extraneous line in the file...  do we care?
                        raise self.Format_Error, ("Assignment outside " +
                                                  "of chip definition @" +
                                                  str(line_number) + " : " +
                                                  repr(line))
            else:
                match = fuse_list_regexp.match(line)
                if (match):
                    (fuse, name, values_string) = match.groups()

                    fuses = entry.setdefault('fuses', {})
                    fuses.setdefault(name, {})

                    values = fuse_value_regexp.findall(values_string)
                    for value_pair in values:
                        (lhs, rhs) = value_pair
                        # rhs may have multiple fuse values, in the form
                        #   xxxx&xxxx&xxxx...
                        # This means that each xxxx applies to the next
                        # consecutive fuse.
                        fuse_values = map(lambda xstr: hex_int(xstr, 16),
                                          rhs.split('&'))
                        fuse_number = int(fuse)
                        fuses[name][lhs] = zip(range(fuse_number - 1,
                                                     (fuse_number +
                                                      len(fuse_values) -
                                                      1)),
                                               fuse_values)
                elif (nonblank_regexp.match(line)):
                    raise self.Format_Error, ('Unrecognized line ' +
                                              'format.  ' + repr(line))

    def get_chip(self, name):
        return ChipInfoEntry(**self.chip_entries[name.lower()])


#-------------------------------------------------


def swab_record(record):
    "Given a record from a hex file, return a new copy with adjacent data bytes swapped."
    result = []

    for x in xrange(0, len(record[1]), 2):
        result += record[1][x + 1]
        result += record[1][x]

    return (record[0], ''.join(result))


#-------------------------------------------------


def range_filter_records(records, lower_bound, upper_bound):
    "Given a list of HEX file records, return a new list of HEX file records containing only the HEX data within the specified address range."
    result = []

    for record in records:
        # Need to handle five cases:
        # 1: record is completely below lower bound - do nothing
        # 2: record is partially below lower bound - slice and append
        # 3: record is in range - append
        # 4: record is partially above upper bound - slice and append
        # 5: record is completely above upper bound - do nothing
        if ((record[0] >= lower_bound) and
            (record[0] < upper_bound)):
            # lower bound is in range and therefore needn't change.
            # Part or all of this record will appear in output.
            if ((record[0] + len(record[1])) < upper_bound):
                # case 3
                result.append(record)
            else:
                # case 4
                slice_length = upper_bound - record[0]
                result.append((record[0], record[1][0:slice_length]))
        elif ((record[0] < lower_bound) and
              ((record[0] + len(record[1])) > lower_bound)):
            # case 2
            slice_pos = (lower_bound - record[0])
            result.append((lower_bound,
                           record[1][slice_pos:len(record[1])]))
    return result


#-------------------------------------------------


def merge_records(records, default_data, base_address = 0):
    "Given a list of HEX file records and a data buffer with its own base address (default=0), merge the HEX file records into a new copy of the data buffer."
    result_list = []

    mark = 0
    point = 0
    for record in records:
        if ((record[0] < base_address) or
            ((record[0] + len(record[1])) > (base_address +
                                             len(default_data)))):
            raise IndexError, 'Record out of range.'

        point = (record[0] - base_address)
        if (mark != point):
            result_list += default_data[mark:point]
            mark = point
        # Now we can add the record data to result_list.
        result_list += record[1]
        mark += len(record[1])
    # Fill out the rest of the result with data from default_data, if
    # necessary.
    if (mark < len(default_data)):
        result_list += default_data[mark:]

    # String-join result_list and return.
    return ''.join(result_list)


#-------------------------------------------------


class Protocol_Interface(object):
    "A convenient interface to the DIY serial/USB PIC programmer kits"
    class Invalid_Response_Error(Exception):
        "Indicates that device did not return the expected response."

    class Invalid_Command_Sequence_Error(Exception):
        "Indicates commands executed in improper order."

    class Invalid_Value_Error(Exception):
        "Indicates incorrect value given for command argument."


    def __init__(self, port):
        self.port = port
        # We need to set the port timeout to a small value and use
        # polling to simulate variable timeouts.  Why?  Because any
        # time you set the timeout in the serial library, DTR goes
        # high, which resets any programmer other than the 149!
        self.port.timeout = .1
        self.vars_set = False
        self.fuses_set = False
        self.reset()


    # _read(count, timeout)
    # Read bytes from the port.  Stop when the requested number of
    # bytes have been received, or the timeout has passed.  In order
    # to sidestep issues with the serial library this is done by
    # polling the serial port's read() method.
    def _read(self, count = 1, timeout = 5):
        result = ''
        init_time = time.time()
        end_time = None
        if (timeout != None):
            end_time = init_time + timeout
        while ((count > 0) and
               ((end_time == None) or
                (time.time() < end_time))):
            read_result = self.port.read(count)
            count = (count - len(read_result))
            result = result + read_result

        return result


    def _core_bits(self):
        self._need_vars()
        core_type = self.vars['core_type']

        if (core_type in [1, 2]):
            return 16
        elif (core_type in [3, 5, 6, 7, 8, 9, 10]):
            return 14
        elif (core_type in [4]):
            return 12
        else:
            return None


    def _expect(self, expected, timeout = 10):
        "Raise an exception if the expected response byte is not sent by the PIC programmer before timeout."
        response = self._read(len(expected), timeout = timeout)
        #print "expect: " + expected + " -> " + response
        if (response != expected):
            raise self.Invalid_Response_Error, ('expected "' +
                                                expected +
                                                '", received ' +
                                                repr(response) +
                                                '.')


    def _need_vars(self):
        if (not self.vars_set):
            raise self.Invalid_Command_Sequence_Error, 'Vars not set'


    def _need_fuses(self):
        if (not self.fuses_set):
            raise self.Invalid_Command_Sequence_Error, 'Fuses not set'


    def reset(self):
        "Resets the PIC Programmer's on-board controller."
        self.vars_set = False
        self.fuses_set = False
        self.firmware_type = None

        self.port.setDTR(True)
        time.sleep(.1)
        self.port.flushInput()
        # Detect whether this unit operates with DTR high, or DTR low.
        self.port.setDTR(False)
        time.sleep(.1)
        # Input was just flushed.  If the unit operates with DTR low,
        # then the unit is now on, and we should be seeing a 2 byte
        # response.
        response = self._read(2, timeout=.3)
        if (response == ''):
            # Apparently the unit operates with DTR high, so...
            self.port.setDTR(True)
            time.sleep(.1)
            response = self._read(2, timeout=.3)

        if (len(response) >= 1):
            result = (response[0] == 'B')
        else:
            result = False
        if (result and (len(response) == 2)):
            self.firmware_type, = struct.unpack('B', response[1])
        return result


    def _command_start(self, cmd = None):
        # Send command 1: if we're at the jump table already this will
        # get us out.  If we're awaiting command start, this will
        # still echo 'Q' and await another command start.
        self.port.write('\x01')
        self._expect('Q')

        # Start command, go to jump table.
        self.port.write('P')

        # Check for acknowledgement
        ack = self._read(1)
        result = (ack == 'P')
        if (not result):
            raise self.Invalid_Response_Error, "No acknowledgement for command start."

        # Send command number, if specified
        if (cmd != None):
            self.port.write(chr(cmd))
        return result


    def _null_command(self):
        cmd = 0
        self.port.write(chr(cmd))
        return None


    def _command_end(self):
        cmd = 1
        self.port.write(chr(cmd))
        ack = self._read(1, timeout=10)
        result = (ack == 'Q')
        if (not result):
            if (ack != ''):
                raise self.Invalid_Response_Error, ("Unexpected response (" +
                                                    ack +
                                                    ") in command end.")
            else:
                raise self.Invalid_Response_Error, "No acknowledgement for command end."
        return result


    def echo(self, msg = 'X'):
        "Instructs the PIC programmer to echo back the message \
        string.  Returns the PIC programmer's response."
        cmd = 2
        self._command_start()
        result = ''
        for c in msg:
            self.port.write(chr(cmd))
            self.port.write(c)
            response = self._read(1)
            result = result + response
        self._command_end()
        return result


    def init_programming_vars(
        self,
        rom_size,
        eeprom_size,
        core_type,
        flag_calibration_value_in_ROM,
        flag_band_gap_fuse,
        flag_18f_single_panel_access_mode,
        flag_vcc_vpp_delay,
        program_delay,
        power_sequence,
        erase_mode,
        program_retries,
        over_program):
        ('Inform PIC programmer of general parameters of PIC to be ' +
         'programmed.  Necessary for use of various other commands.')

        cmd = 3
        self._command_start(cmd)

        flags = ((flag_calibration_value_in_ROM and 1) |
                 (flag_band_gap_fuse and 2) |
                 (flag_18f_single_panel_access_mode and 4) |
                 (flag_vcc_vpp_delay and 8))


        command_payload = struct.pack('>HHBBBBBBB',
                                      rom_size,
                                      eeprom_size,
                                      core_type,
                                      flags,
                                      program_delay,
                                      power_sequence,
                                      erase_mode,
                                      program_retries,
                                      over_program)
        self.port.write(command_payload)
        response = self._read(1)
        self._command_end()

        result = (response == 'I')
        if (result):
            self.vars = {'rom_size' : rom_size,
                         'eeprom_size' : eeprom_size,
                         'core_type' : core_type,
                         'flag_calibration_value_in_ROM' : flag_calibration_value_in_ROM,
                         'flag_band_gap_fuse' : flag_band_gap_fuse,
                         'flag_18f_single_panel_access_mode' : flag_18f_single_panel_access_mode,
                         'flag_vcc_vpp_delay' : flag_vcc_vpp_delay,
                         #'flags' : flags,
                         'program_delay' : program_delay,
                         'power_sequence' : power_sequence,
                         'erase_mode' : erase_mode,
                         'program_retries' : program_retries,
                         'over_program' : over_program}
            self.vars_set = True
        else:
            del(self.vars)
            self.vars_set = False
        return result


    def _set_programming_voltages_command(self, on):
        """Turn the PIC programming voltages on or off.  Must be called as part of other commands which read or write PIC data."""
        cmd_on = 4
        cmd_off = 5

        self._need_vars()
        if (on):
            self.port.write(chr(cmd_on))
            expect = 'V'
        else:
            self.port.write(chr(cmd_off))
            expect = 'v'
        response = self._read(1)
        return (response == expect)


    def cycle_programming_voltages(self):
        cmd = 6
        self._need_vars()
        self._command_start(cmd)
        response = self._read(1)
        self._command_end()
        return (response == 'V')


    def program_rom(self, data):
        "Write data to ROM.  data should be a binary string of data, high byte first."
        cmd = 7
        self._need_vars()

        word_count = (len(data) // 2)
        if (self.vars['rom_size'] < word_count):
            raise self.Invalid_Value_Error, "Data too large for PIC ROM"

        if (((word_count * 2) % 32) != 0):
            raise self.Invalid_Value_Error, "ROM data must be a multiple of 32 bytes in size."

        self._command_start()
        self._set_programming_voltages_command(True)
        self.port.write(chr(cmd))

        word_count_message = struct.pack('>H', word_count)
        self.port.write(word_count_message)

        self._expect('Y', timeout=20)
        try:
            for i in xrange(0, (word_count * 2), 32):
                self.port.write(data[i:(i + 32)])
                self._expect('Y', timeout=20)
            self._expect('P', timeout=20)
        except self.Invalid_Response_Error:
            self.port.flushInput()    #We don't get current address for now.
            return False

        self._set_programming_voltages_command(False)
        self._command_end()
        return True


    def program_eeprom(self, data):
        "Write data to EEPROM.  Data size must be small enough to fit in EEPROM."
        cmd = 8
        self._need_vars()

        byte_count = len(data)
        if (self.vars['eeprom_size'] < byte_count):
            raise self.Invalid_Value_Error, "Data too large for PIC EEPROM"

        if ((byte_count % 2) != 0):
            raise self.Invalid_Value_Error, "EEPROM data must be a multiple of 2 bytes in size."

        self._command_start()
        self._set_programming_voltages_command(True)
        self.port.write(chr(cmd))

        byte_count_message = struct.pack('>H', byte_count)
        self.port.write(byte_count_message)

        self._expect('Y', timeout=20)
        for i in xrange(0, byte_count, 2):
            self.port.write(data[i:(i + 2)])
            self._expect('Y', timeout=20)
        # We must send an extra two bytes, which will have no effect.
        # Why?  I'm not sure.  See protocol doc, and read it backwards.
        # I'm sending zeros because if we did wind up back at the
        # command jump table, then the zeros will have no effect.
        self.port.write('\x00\x00')
        self._expect('P', timeout = 20)

        self._set_programming_voltages_command(False)
        self._command_end()
        return True


    def program_id_fuses(self, id, fuses):
        "Program PIC ID and fuses.  For 16-bit processors, fuse values \
        are not committed until program_18fxxxx_fuse() is called."
        cmd = 9
        self._need_vars()

        core_bits = self._core_bits()
        if (core_bits == 16):
            if (len(id) != 8):
                raise self.Invalid_Value_Error, 'Should have 8-byte ID for 16 bit core.'
            if (len(fuses) != 7):
                raise self.Invalid_Value_Error, 'Should have 7 fuses for 16 bit core.'
            command_body = ('00' + id + struct.pack('<HHHHHHH', *fuses))
            response_ok = 'Y'
            response_bad = 'N'  # Protocol doc doesn't give a "bad" response value.
        else:
            if (len(fuses) != 1):
                raise self.Invalid_Value_Error, 'Should have one fuse for 14 bit core.'
            if (len(id) != 4):
                raise self.Invalid_Value_Error, 'Should have 4-byte ID for 14 bit core.'
            # Command starts with dual '0' for 14 bit
            command_body = ('00' + id + 'FFFF' +
                            struct.pack('<H', fuses[0]) + ('\xff\xff' * 6))
            response_ok = 'Y'
            response_bad = 'N'

        self._command_start()
        self._set_programming_voltages_command(True)
        self.port.write(chr(cmd))

        self.port.write(command_body)

        response = self._read(timeout = 20)

        self._set_programming_voltages_command(False)
        self._command_end()

        if (response == response_ok):
            self.fuses_set = True

        return (response == response_ok)



    def read_rom(self):
        "Returns contents of PIC ROM as a string of big-endian values."
        cmd = 11
        self._need_vars()

        # vars['rom_size'] is in words.  So multiply by two to get bytes.
        rom_size = self.vars['rom_size'] * 2

        self._command_start()
        self._set_programming_voltages_command(True)
        self.port.write(chr(cmd))

        response = self._read(rom_size)

        self._set_programming_voltages_command(False)
        self._command_end()
        return data_string.data_string(response)


    def read_eeprom(self):
        "Returns data stored in PIC EEPROM."
        cmd = 12
        self._need_vars()

        eeprom_size = self.vars['eeprom_size']

        self._command_start()
        self._set_programming_voltages_command(True)
        self.port.write(chr(cmd))
        response = self._read(eeprom_size)
        self._set_programming_voltages_command(False)
        self._command_end()
        return data_string.data_string(response)


    def read_config(self):
        "Reads chip ID and programmed ID, fuses, and calibration."
        cmd = 13
        self._command_start()
        self._set_programming_voltages_command(True)
        self.port.write(chr(cmd))
        ack = self._read(1)
        if (ack != 'C'):
            raise self.Invalid_Response_Error, "No acknowledgement from read_config()"
        response = self._read(26)
        self._set_programming_voltages_command(False)
        self._command_end()

        config = struct.unpack('<HccccccccHHHHHHHH', response)
        result = {'chip_id' : config[0],
                  'id' : ''.join(config[1:9]),
                  'fuses' : list(config[9:16]),
                  'calibrate' : config[16]}
        return result


    def erase_chip(self):
        "Erases all data from chip."
        cmd = 14
        self._need_vars()

        self._command_start(cmd)
        response = self._read(1)
        self._command_end()
        return (response == 'Y')


    def rom_is_blank(self, high_byte):
        "Returns True if PIC ROM is blank."
        cmd = 15
        self._need_vars()

        expected_b_bytes = (self.vars['rom_size'] // 256) - 1
        self._command_start(cmd)
        self.port.write(high_byte)
        while True:
            response = self._read(1)
            if (response == 'Y'):
                self._command_end()
                return True
            if (response == 'N'):
                self._command_end()
                return False
            if (response == 'C'):
                self._command_end()
                return False
            if (response == 'B'):
                if (expected_b_bytes <= 0):
                    raise self.Invalid_Response_Error, "Received wrong number of 'B' bytes in rom_is_blank()"
                expected_ff_bytes -= 1
            else:
                raise self.Invalid_Response_Error, "Unexpected byte in rom_is_blank(): " + response


    def eeprom_is_blank(self):
        "Returns True if PIC EEPROM is blank."
        cmd = 16
        self._command_start(cmd)
        response = self._read(1)
        self._command_end()
        if ((response != 'Y') and
            (response != 'N')):
            raise self.Invalid_Response_Error, 'Unexpected response in eeprom_is_blank(): ' + response

        return (response == 'Y')


    def program_18fxxxx_fuse(self):
        "Commits fuse values previously loaded using program_id_fuses()"
        cmd = 17

        self._need_vars()
        self._need_fuses()
        self._command_start(cmd)
        # It appears the command will return 'B' on chips for which
        # this isn't appropriate?
        response = self._read(1)
        result = response == 'Y'
        self._command_end()

        return result


    def wait_until_chip_in_socket(self):
        "Blocks until a chip is inserted in the programming socket."
        cmd = 18

        self._command_start(cmd)
        self._expect('A')
        result = False

        self._expect('Y', timeout=None)
        self._command_end()
        return True


    def wait_until_chip_out_of_socket(self):
        "Blocks until chip is removed from programming socket."
        cmd = 19

        self._command_start(cmd)
        self._expect('A')
        result = False

        self._expect('Y', timeout=None)
        self._command_end()
        return True


    def programmer_firmware_version(self):
        "Returns the PIC programmer's numeric firmware version."
        cmd = 20
        self._command_start(cmd)
        response = self._read(1)
        self._command_end()
        result, = struct.unpack('B', response)
        return result


    def programmer_protocol(self):
        "Returns the PIC programmer's protocol version in text form."
        cmd = 21
        self._command_start(cmd)
        # Protocol doc isn't clear on the format of command 22's output.
        # Presumably it will always be exactly 4 bytes.
        response = self._read(4)
        self._command_end()
        return response


    def program_debug_vector(self, address):
        "Sets the PIC's debugging vector."
        cmd = 22
        self._need_vars()

        BE4_address = struct.pack('>I', address)
        self._command_start(cmd)
        self.port.write(BE4_address[1:4])
        response = self._read(1)
        self._command_end()

        if ((response != 'Y') and
            (response != 'N')):
            raise self.Invalid_Response_Error, 'Unexpected response in program_debug_vector(): ' + response

        return (response == 'Y')


    def read_debug_vector(self):
        "Returns the value of the PIC's debugging vector."
        cmd = 23
        self._need_vars()

        self._command_start(cmd)
        response = self._read(4)
        BE4_address = '\x00' + response[1:4]
        result, = struct.unpack('>I', BE4_address);
        self._command_end()

        return result


#-------------------------------------------------


def indexwise_and(fuses, setting_values):
    ('Given a list of fuse values, and a list of (index, value) pairs, ' +
     'return a list x such that x[index] = fuses[index] & value.')

    result = [x for x in fuses]
    for (index, value) in setting_values:
        result[index] = result[index] & value
    return result


#-------------------------------------------------

#Ooh, look - a Wrangler...
class prot_interface_wrangler(object):
    def __init__(self,
                 pic_type,
                 port = '/dev/ttyS0',
                 chipinfo_filename = 'chipinfo.cid'):
        self.port = serial.Serial(port, 19200, timeout = 10)
        self.chipinfo_reader = Chipinfo_Reader(chipinfo_filename)
        self.chip = self.chipinfo_reader.get_chip(pic_type)
        self.prot_interface = Protocol_Interface(self.port)
        self.prot_interface.init_programming_vars(**self.chip.get_programming_vars())

    def set_chip(self,
                 pic_type):
        self.chip = self.chipinfo_reader.get_chip(pic_type)
        self.prot_interface.init_programming_vars(**self.chip.get_programming_vars())


#--------------------------------------------------


def program_pic(port, pic_type, hex_file_name = '',
                program = True,
                fuses = None, ID = None,
                hex_file = None, icsp_mode = False):
    ("Given a serial port ID, PIC type, hex file name, and other optional " +
     "data, attempt to program the hex file data to a PIC in the programmer.")
    try:
        s = serial.Serial(port = port, baudrate = 19200,
                          bytesize = 8, parity = 'N', stopbits = 1,
                          timeout = 10, xonxoff = 0, rtscts = 0)
    except serial.SerialException:
        print 'Unable to open serial port "' + port + '".'
        print 'Be sure port identifier is valid and that you have access to it.'
        return False

    # Get chip info
    chipinfo_filename = module_location + 'chipinfo.cid'
    try:
        chipinfo_reader = Chipinfo_Reader(chipinfo_filename)
    except IOError:
        print 'Unable to locate chipinfo.cid file.'
        print 'Please verify that file is present in the same directory as this script, and that the filename is in lowercase characters, and that you have access to read the file.'
        return False

    try:
        chip_info = chipinfo_reader.get_chip(pic_type)
    except KeyError:
        print 'Unable to find chip type "' + pic_type + '" in data file.'
        print 'Please check that the spelling is correct and that data file is up to date.'
        return False

    # Generate blank ROM and EEPROM of appropriate size.
    rom_blank_word = 0xffff << chip_info.get_core_bits()
    rom_blank_word = (~rom_blank_word & 0xffff)
    rom_blank_bytes = struct.pack('>H', rom_blank_word)
    rom_blank = rom_blank_bytes * chip_info.vars['rom_size']

    eeprom_blank_byte = '\xff'
    eeprom_blank = eeprom_blank_byte * chip_info.vars['eeprom_size']

    # Read hex file.
    try:
        hex_file = hex_file_reader.Hex_File_Reader(hex_file_name)
    except IOError:
        print 'Unable to find hex file "' + hex_file_name + '".'
        print 'Please verify that the file exists and that you have access to it.'
        return False

    rom_word_base = 0x0000
    config_word_base = 0x4000
    eeprom_word_base = 0x4200
    rom_word_end = config_word_base
    config_word_end = 0x4010
    eeprom_word_end = 0xffff

    # Filter hex file data into ROM, config, and EEPROM:
    rom_records = range_filter_records(hex_file.records,
                                       rom_word_base,
                                       rom_word_end)

    config_records = range_filter_records(hex_file.records,
                                          config_word_base,
                                          config_word_end)

    eeprom_records = range_filter_records(hex_file.records,
                                          eeprom_word_base,
                                          eeprom_word_end)

    # Try to detect whether the ROM data is big-endian or
    # little-endian.  If it is little-endian, swap bytes.
    swap_bytes = None
    for record in rom_records:
        if (record[0] % 2 != 0):
            raise ValueError, 'ROM record starts on odd address.'
        for x in xrange(0, len(record[1]), 2):
            if ((x + 2) < len(record[1])):
                BE_word, = struct.unpack('>H', record[1][x:x+2])
                LE_word, = struct.unpack('<H', record[1][x:x+2])

                BE_ok = ((BE_word & rom_blank_word) == BE_word)
                LE_ok = ((LE_word & rom_blank_word) == LE_word)

                if (BE_ok and not LE_ok):
                    swap_bytes = False
                    break
                elif (LE_ok and not BE_ok):
                    swap_bytes = True
                    break
                elif (not (LE_ok or BE_ok)):
                    raise ValueError, ('Invalid ROM word: ' +
                                       hex(LE_word) +
                                       ', ROMblank: ' +
                                       hex(rom_blank_word))
        if (swap_bytes != None):
            break
    if (swap_bytes):
        rom_records = map(swab_record, rom_records)
        config_records = map(swab_record, config_records)

    # EEPROM is stored in the hex file with one byte per word, so we
    # need to pick one of the two bytes out of each word to program.
    # If swap_bytes is true, then file is little-endian, and we want
    # the first byte of each EEPROM word.  Else we want the second.
    if (swap_bytes):
        pick_byte = 0
    else:
        pick_byte = 1
    eeprom_records = map(
        lambda record: ((eeprom_word_base +
                         ((record[0] - eeprom_word_base) / 2)),
                        (''.join([record[1][x] for x in xrange(pick_byte,
                                                               len(record[1]),
                                                               2)]))),
        eeprom_records)



    # FINALLY!  We create the byte-level data...
    rom_data = merge_records(rom_records, rom_blank)
    eeprom_data = merge_records(eeprom_records, eeprom_blank, 0x4200)

    # Extract fuse data, ID data, etc. from fuse records
    if (ID != None):
        id_data = ID
    else:
        id_data = merge_records(
            range_filter_records(config_records, 0x4000, 0x4008),
            ('\x00' * 8))
        # If this is a 16-bit core, leave id_data as-is.  Else we need to
        # take every other byte according to endian-ness.
        if (chip_info.get_core_bits() != 16):
            id_data = ''.join([id_data[x] for x in xrange(pick_byte, 8, 2)])
        ID = id_data

    # Pull fuse data from config records
    fuse_data = ''.join(map(lambda word: struct.pack('>H', word),
                            chip_info.vars['FUSEblank']))
    fuse_data = merge_records(
        range_filter_records(config_records, 0x400e, 0x4010),
        fuse_data,
        0x400e)

    # Go through each fuse listed in chip info.
    # Determine its current setting in fuse_value, and accumulate a new
    # fuse_value by incorporating values specified in (fuses).
    fuse_error = False
    fuse_values = [hex_int(struct.unpack('>H', fuse_data[x:x+2])[0])
                   for x in xrange(0, len(fuse_data), 2)]
    #for i in xrange(0, len(fuse_blank)):
    #fuse_value[i] = struct.unpack('>H', fuse_data[i*2, i*2+2])
    if (fuses):
        fuse_settings = chip_info.decode_fuse_data(fuse_values)
        fuse_settings.update(fuses)
        try:
            fuse_values = chip_info.encode_fuse_data(fuse_settings)
        except ChipInfoEntry.Fuse_Error:
            print 'Invalid fuse setting.  Fuse names and valid settings for this chip are as follows:'
            print chip_info.fuse_doc()
            return False


    try:
        # Perhaps now, at last, we can program some kind of a PIC.
        # Start up protocol interface
        prot_interface = Protocol_Interface(s)

        # Verify that communications are functioning
        response = prot_interface.echo(hex_file_name)
        if (response != hex_file_name):
            print 'Invalid response received from PIC programmer.'
            print 'Please check that device is properly connected and working.'
    except Protocol_Interface.Invalid_Response_Error:
        print 'Unable to initialize connection to programmer.'
        print 'Please check that device is properly connected and working.'
        return False

    # Initialize programming variables
    programming_vars = chip_info.get_programming_vars()
    if (icsp_mode):
        power_sequence = programming_vars['power_sequence']
        if (power_sequence == 2):
            power_sequence = 1
        elif (power_sequence == 4):
            power_sequence = 3
        programming_vars['power_sequence'] = power_sequence

    prot_interface.init_programming_vars(**programming_vars)

    try:
        # Instruct user to insert chip
        if (not icsp_mode):
            print 'Waiting for user to insert chip into socket with pin 1 at ' + chip_info.pin1_location_text()
            prot_interface.wait_until_chip_in_socket()
            print 'Chip detected.'
        else:
            print 'Accessing chip connected to ICSP port.'

        # If write mode is active, program the ROM, EEPROM, ID and fuses.
        if (program):
            # Write ROM, EEPROM, ID and fuses
            print 'Erasing Chip'
            if (not prot_interface.erase_chip()):
                print 'Erasure failed.'

            print 'Programming ROM'
            if (not prot_interface.program_rom(rom_data)):
                print 'ROM programming failed.'

            if (chip_info.has_eeprom()):
                print 'Programming EEPROM'
            if (not prot_interface.program_eeprom(eeprom_data)):
                print 'EEPROM programming failed.'

            print 'Programming ID and fuses'
            if (not prot_interface.program_id_fuses(ID, fuse_values)):
                print 'Programming ID and fuses failed.'

        # Verify programmed data.
        # Behold, my godlike powers of verification:
        print 'Verifying ROM'
        pic_rom_data = prot_interface.read_rom()
        verification_result = True

        if (pic_rom_data == rom_data):
            print 'ROM verified.'
        else:
            print 'ROM verification failed.'
            verification_result = False

        if (chip_info.has_eeprom()):
            print 'Verifying EEPROM'
            pic_eeprom_data = prot_interface.read_eeprom()
            if (pic_eeprom_data == eeprom_data):
                print 'EEPROM verified.'
            else:
                print 'EEPROM verification failed.'
                verification_result = False

        if (verification_result and (chip_info.get_core_bits() == 16)):
            print "Committing 18Fxxxx fuse data."
            prot_interface.program_18fxxxx_fuse()

    except Protocol_Interface.Invalid_Response_Error:
        print 'Error: Communication failure.  This may be a bug in this script or a problem with your programmer hardware.'
        return False

    return verification_result


# Ugh, as much as I hate having to put this in at all, I despise
# having to put it at the end...
if (__name__ == '__main__'):
    handle_command_line(sys.argv)

