from picpro.protocol.IProgrammingInterface import IProgrammingInterface
from picpro.protocol.IFuseTransaction import IFuseTransaction


# @TODO Missing commands to implement: 24.
class FuseTransaction(IFuseTransaction):

    def __init__(self, programming_interface):
        super().__init__(programming_interface)
        self.cmd_program_18fxxxx_fuse = 17


class ProgrammingInterface(IProgrammingInterface):

    def __init__(self, connection, chip_info, icsp_mode=False):
        super().__init__(connection, chip_info, icsp_mode)
        self.cmd_init_programming_vars = 3
        self.cmd_programming_voltages_command_on = 4
        self.cmd_programming_voltages_command_off = 5
        self.cmd_cycle_programming_voltages = 6
        self.cmd_program_rom = 7
        self.cmd_program_eeprom = 8
        self.cmd_program_id_fuses = 9
        self.cmd_program_calibration = 10
        self.cmd_read_rom = 11
        self.cmd_read_eeprom = 12
        self.cmd_read_config = 13
        self.cmd_erase_chip = 14
        self.cmd_rom_is_blank = 15
        self.cmd_eeprom_is_blank = 16
        self.cmd_program_debug_vector = 22
        self.cmd_read_debug_vector = 23
