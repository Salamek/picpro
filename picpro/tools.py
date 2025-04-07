
def indexwise_and(fuses: list, setting_values: list) -> list:
    """Given a list of fuse values, and a list of (index, value) pairs,
    return a list x such that x[index] = fuses[index] & value."""

    result = list(fuses)
    for (index, value) in setting_values:
        result[index] = result[index] & value
    return result


def swab_bytes(to_swab: bytes) -> bytes:
    result = bytearray()
    for x in range(0, len(to_swab), 2):
        result.append(to_swab[x + 1])
        result.append(to_swab[x])

    return bytes(result)
