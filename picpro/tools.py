from typing import Tuple


def indexwise_and(fuses: list, setting_values: list) -> list:
    """Given a list of fuse values, and a list of (index, value) pairs,
    return a list x such that x[index] = fuses[index] & value."""

    result = list(fuses)
    for (index, value) in setting_values:
        result[index] = result[index] & value
    return result


def swab_bytes(to_swab: bytes) -> bytearray:
    result = bytearray()
    for x in range(0, len(to_swab), 2):
        result.append(to_swab[x + 1])
        result.append(to_swab[x])

    return result


def swab_record(record: list) -> Tuple[int, bytearray]:
    """Given a record from a hex file, return a new copy with adjacent data bytes swapped."""
    #result = bytearray()
    #for x in range(0, len(record[1]), 2):
    #    result.append(record[1][x + 1])
    #    result.append(record[1][x])

    return record[0], swab_bytes(record[1])


def range_filter_records(records: list, lower_bound: int, upper_bound: int) -> list:
    """Given a list of HEX file records, return a new list of HEX file records containing only the HEX data within the specified address range."""
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
            if (record[0] + len(record[1])) < upper_bound:
                # case 3
                result.append(record)
            else:
                # case 4
                slice_length = upper_bound - record[0]
                result.append((record[0], record[1][0:slice_length]))
        elif record[0] < lower_bound < (record[0] + len(record[1])):
            # case 2
            slice_pos = (lower_bound - record[0])
            result.append((lower_bound, record[1][slice_pos:len(record[1])]))
    return result


def merge_records(records: list, default_data: bytes, base_address: int = 0) -> bytearray:
    """Given a list of HEX file records and a data buffer with its own base address (default=0), merge the HEX file records into a new copy of the data buffer."""
    result_list = bytearray()
    mark = 0
    for record in records:
        if record[0] < base_address:
            raise IndexError('Record address out of range.')

        if (record[0] + len(record[1])) > (base_address + len(default_data)):
            raise IndexError('Record out of range.')

        point = (record[0] - base_address)
        if mark != point:
            result_list += default_data[mark:point]
            mark = point
        # Now we can add the record data to result_list.
        result_list += record[1]
        mark += len(record[1])
    # Fill out the rest of the result with data from default_data, if
    # necessary.
    if mark < len(default_data):
        result_list += default_data[mark:]

    # String-join result_list and return.
    return result_list
