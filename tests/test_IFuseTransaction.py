from typing import cast
from unittest.mock import create_autospec

import pytest

from picpro.protocol.IFuseTransaction import IFuseTransaction
from picpro.protocol.IProgrammingInterface import IProgrammingInterface


@pytest.fixture
def programming_interface() -> IProgrammingInterface:
    return cast('IProgrammingInterface', create_autospec(IProgrammingInterface, instance=True))


def test_retains_programming_interface(programming_interface: IProgrammingInterface) -> None:
    transaction = IFuseTransaction(programming_interface)
    assert transaction.programming_interface is programming_interface


def test_fuse_commit_requires_implementation(programming_interface: IProgrammingInterface) -> None:
    transaction = IFuseTransaction(programming_interface)
    with pytest.raises(NotImplementedError):
        transaction.program_18fxxxx_fuse([0xffff] * 7)
