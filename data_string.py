import struct

def _hex(byte):
    hex_chars = '0123456789abcdef'
    result = hex_chars[byte / 16] + hex_chars[byte % 16]
    return result

class data_string(str):
    def __init__(self, src_string):
        self._data = src_string

    def __repr__(self):
        result_list = ["'"]

        for c in self._data:
            hex_char = _hex(struct.unpack('B', c)[0])
            result_list.append(r'\x' + hex_char)
        result_list.append("'")

        return ''.join(result_list)
