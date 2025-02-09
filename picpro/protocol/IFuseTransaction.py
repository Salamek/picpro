from typing import List

from picpro.protocol.IProgrammingInterface import IProgrammingInterface


class IFuseTransaction:
    def __init__(self, programming_interface: IProgrammingInterface):
        self.programming_interface = programming_interface

    def program_18fxxxx_fuse(self, fuses: List[int]) -> None:
        raise NotImplementedError
