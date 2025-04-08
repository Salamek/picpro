from picpro.protocol.IConnection import IConnection


class Connection(IConnection):

    expected_programmer_protocol = b'P18A'

    def __init__(self, port):
        super().__init__(port)
        self.cmd_wait_until_chip_in_socket = 18
        self.cmd_wait_until_chip_out_of_socket = 19
        self.cmd_programmer_version = 20
        self.cmd_programmer_protocol = 21
