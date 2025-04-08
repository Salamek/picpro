from typing import List
import struct

from picpro.protocol.IProgrammingInterface import IProgrammingInterface
from picpro.exceptions import InvalidResponseError


class IFuseTransaction:
    def __init__(self, programming_interface: IProgrammingInterface):
        self.programming_interface = programming_interface
        self.cmd_program_18fxxxx_fuse = 0

    def program_18fxxxx_fuse(self, fuses: List[int]) -> None:
        """Commits fuse values previously loaded using program_id_fuses()"""
        cmd = self.cmd_program_18fxxxx_fuse

        command_body = (b'\x00' * 10) + struct.pack('<HHHHHHH', *fuses)  # send all 0 in id, and then the fuse values
        self.programming_interface.connection.command_start()
        self.programming_interface.set_programming_voltages_command(True)
        self.programming_interface.connection.serial_connection.write(cmd.to_bytes(1, 'little'))
        self.programming_interface.connection.serial_connection.write(command_body)
        # It appears the command will return 'B' on chips for which
        # this isn't appropriate?
        response = self.programming_interface.connection.read(1)
        result = response == b'Y'
        self.programming_interface.set_programming_voltages_command(False)
        self.programming_interface.connection.command_end()

        if not result:
            raise InvalidResponseError
