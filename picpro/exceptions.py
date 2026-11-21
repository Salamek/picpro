class FormatError(Exception):
    """Indicates an error in the chipinfo file's format."""


class FuseError(Exception):
    """Indicates an erroneous fuse value."""


class InvalidResponseError(Exception):
    """Indicates that device did not return the expected response."""


class InvalidCommandSequenceError(Exception):
    """Indicates commands executed in improper order."""


class InvalidValueError(Exception):
    """Indicates incorrect value given for command argument."""


class InvalidRecordError(Exception):
    """Indicates an improperly formatted HEX record."""


class InvalidChecksumError(Exception):
    """Indicates a failed checksum test."""


class UnknownChipError(KeyError):
    """The requested chip has no definition."""


class InvalidFirmwareError(ValueError):
    """The firmware data does not fit the selected chip."""


class InvalidPicIdError(ValueError):
    """The PIC ID override has invalid hexadecimal data or the wrong length."""


class ICSPRequiredError(ValueError):
    """The selected chip can only be programmed through ICSP."""


class UnsupportedChipError(ValueError):
    """The chip parameters are not supported by the programmer protocol."""
