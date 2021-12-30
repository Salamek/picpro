import re
import struct
import data_string

class Hex_File_Reader(object):
    class Invalid_Record_Error(Exception):
        "Indicates an improperly formatted HEX record."

    class Invalid_Checksum_Error(Exception):
        "Indicates a failed checksum test."

    def __init__(self, file_name = '', file = None):
        if (file == None):
            file = open(file_name, 'U')

        ext_address = 0
        self.records = []
        eof = False
        for line in file:
            hex_record_regexp = re.compile(r'^:[0-9a-fA-F]+$')
            hex_record_chopper = re.compile(r'^:(..)(....)(..)(.*)(..)$')
            if (hex_record_regexp.match(line)):
                if (eof):
                    raise Invalid_Record_Error, 'extra record after EOF record.'
                chop = hex_record_chopper.match(line)
                (length_str,
                 address_str,
                 type_str,
                 data_str,
                 checksum_str) = chop.groups()
                length = int(length_str, 16)
                address = int(address_str, 16)
                type = int(type_str, 16)
                data = data_string.data_string(''.join([chr(int(data_str[x:x+2], 16)) for x in xrange(0, len(data_str), 2)]))
                checksum = int(checksum_str, 16)

                if (length != len(data)):
                    raise Invalid_Record_Error, 'Incorrect data length: ' + str(length) + ' != ' + str(len(data))

                checksum_test = 0
                for x in xrange(1, len(line) - 4, 2):
                    checksum_test = (checksum_test + int(line[x:x+2], 16)) % 256
                checksum_test = (256 - checksum_test) % 256
                if (checksum_test != checksum):
                    raise self.Invalid_Checksum_Error, str(checksum_test) + ' != ' + str(checksum)

                if (type == 0):
                    # data record
                    self.records.append(((address | ext_address),
                                         data))
                elif (type == 1):
                    # EOF record
                    eof = True
                elif (type == 2):
                    # Ext. linear address record
                    ext_address = struct.unpack('>H', data)[0] << 16
                elif (type == 4):
                    ext_address = struct.unpack('>H', data)[0] << 4
                else:
                    raise self.Invalid_Record_Error, 'Unknown record type (' + str(type) + ')'
            elif (len(line) != 0):
                raise self.Invalid_Record_Error, 'Record does not start with colon:  ' + line


    def merge(self, data_str):
        data_list = list(data_str)

        for record in self.records:
            (address, data) = record

            if ((address + len(data)) > len(data_list)):
                raise IndexError, 'Data record out of range.'

            data_list[address:address + len(data)] = data

        return data_string.data_string(''.join(data_list))
