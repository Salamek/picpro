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
