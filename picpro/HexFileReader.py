import re
import struct

from picpro.exceptions import InvalidRecordError, InvalidChecksumError


class HexFileReader:
    def __init__(self, file_name: str):
        with open(file_name, 'r', encoding='ascii') as file:

            ext_address = 0
            self.records = []
            eof = False
            for line in file:
                hex_record_regexp = re.compile(r'^:[0-9a-fA-F]+$')
                hex_record_chopper = re.compile(r'^:(..)(....)(..)(.*)(..)$')
                if hex_record_regexp.match(line):
                    if eof:
                        raise InvalidRecordError('extra record after EOF record.')
                    chop = hex_record_chopper.match(line)
                    if not chop:
                        raise InvalidRecordError('failed to parse line {}'.format(line))
                    length_str, address_str, type_str, data_str, checksum_str = chop.groups()
                    length = int(length_str, 16)
                    address = int(address_str, 16)
                    record_type = int(type_str, 16)
                    data = bytearray.fromhex(data_str)
                    checksum = int(checksum_str, 16)

                    if length != len(data):
                        raise InvalidRecordError('Incorrect data length: {} != {} ({})'.format(length, len(data), data_str))

                    checksum_test = 0
                    for x in range(1, len(line) - 4, 2):
                        checksum_test = (checksum_test + int(line[x:x + 2], 16)) % 256
                    checksum_test = (256 - checksum_test) % 256
                    if checksum_test != checksum:
                        raise InvalidChecksumError('{} != {}'.format(checksum_test, checksum))

                    if record_type == 0:
                        # data record
                        self.records.append(((address | ext_address), data))
                    elif record_type == 1:
                        # EOF record
                        eof = True
                    elif record_type == 2:
                        # Ext. linear address record
                        ext_address = struct.unpack('>H', data)[0] << 16
                    elif record_type == 4:
                        ext_address = struct.unpack('>H', data)[0] << 4
                    else:
                        raise InvalidRecordError('Unknown record type ({})'.format(record_type))
                elif len(line) != 0:
                    raise InvalidRecordError('Record does not start with colon:  {}'.format(line))

    def merge(self, data_str: bytes) -> bytes:
        data_list = bytearray(data_str)

        for record in self.records:
            (address, data) = record

            if (address + len(data)) > len(data_list):
                raise IndexError('Data record out of range.')

            data_list[address:address + len(data)] = data

        return bytes(data_list)
