import struct

from picpro.ChipInfoEntry import ChipInfoEntry
from picpro.protocol.IConnection import IConnection
from picpro.protocol.IProgrammingInterface import IProgrammingInterface
from picpro.protocol.p18a.ProgrammingInterface import ProgrammingInterface


class Connection(IConnection):

    expected_programmer_protocol = b'P18A'

    def wait_until_chip_in_socket(self) -> None:
        """Blocks until a chip is inserted in the programming socket."""
        cmd = 18
        self.command_start(cmd)
        self.expect(b'A')

        self.expect(b'Y', timeout=None, send_command_end=True)


    def wait_until_chip_out_of_socket(self) -> None:
        """Blocks until chip is removed from programming socket."""
        cmd = 19

        self.command_start(cmd)
        self.expect(b'A')

        self.expect(b'Y', timeout=None, send_command_end=True)


    def programmer_version(self) -> bytes:
        """Returns the PIC programmer's numeric version.
        K128     = 0  (Byte)
        K149-A   = 1  (Byte)
        K149-B   = 2  (Byte)
        K150     = 3  (Byte)
        """
        cmd = 20
        self.command_start(cmd)
        response = self.read(1)
        self.command_end()
        result, = struct.unpack('B', response)
        return result

    def programmer_protocol(self) -> bytes:
        """Returns the PIC programmer's protocol version in text form."""
        cmd = 21
        self.command_start(cmd)
        # Protocol doc isn't clear on the format of command 22's output.
        # Presumably it will always be exactly 4 bytes.
        response = self.read(4)
        self.command_end()
        return response


    def get_programming_interface(self, chip_info: ChipInfoEntry, icsp_mode: bool = False) -> IProgrammingInterface:
        return ProgrammingInterface(self, chip_info, icsp_mode)
