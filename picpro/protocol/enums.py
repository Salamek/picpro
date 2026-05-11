import enum


class ResponseEnum(enum.Enum):
    YES = b'Y'
    NO = b'N'
    INITIALIZED = b'I'
    PROGRAMING_VOLTAGE_ENABLED = b'V'
    PROGRAMING_VOLTAGE_DISABLED = b'v'
    AT_COMMAND_JUMP_TABLE = b'P'
    INCORRECT_BYTES = b'B'
    WAITING_FOR_ACTION = b'A'
    WAITING_FOR_COMMAND = b'Q'


class HeaderEnum(enum.Enum):
    CONFIGURATION = b'C'
    PROGRAMMER_VERSION = b'B'
