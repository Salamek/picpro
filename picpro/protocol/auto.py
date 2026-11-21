from picpro.exceptions import InvalidResponseError
from picpro.protocol.IConnection import IConnection
from picpro.protocol.p014.Connection import Connection as P014Connection
from picpro.protocol.p016.Connection import Connection as P016Connection
from picpro.protocol.p018.Connection import Connection as P018Connection
from picpro.protocol.p18a.Connection import Connection as P18AConnection

_CONNECTIONS: dict[bytes, type[IConnection]] = {
    b'P014': P014Connection,
    b'P016': P016Connection,
    b'P018': P018Connection,
    b'P18A': P18AConnection,
}
_PROTOCOL_PREFIX = b'P'


def _detect_protocol(connection: IConnection) -> bytes:
    # Command 21 is GET PROTOCOL on P18A and GET VERSION on P014/16/18.
    connection.command_start(21)
    first = connection.read(1)
    if first == _PROTOCOL_PREFIX:
        protocol = first + connection.read(3)
        connection.command_end()
        if protocol != P18AConnection.expected_programmer_protocol:
            msg = f'Unsupported or invalid programmer protocol: {protocol!r}.'
            raise InvalidResponseError(msg)
    else:
        connection.command_end()
        if first != bytes([connection.detected_programmer_version]) or first not in (b'\x00', b'\x01', b'\x02', b'\x03'):
            msg = f'Invalid programmer version response during protocol detection: {first!r}.'
            raise InvalidResponseError(msg)
        connection.command_start(22)
        protocol = connection.read(4)
        connection.command_end()
        if protocol not in (P014Connection.expected_programmer_protocol, P016Connection.expected_programmer_protocol,
                            P018Connection.expected_programmer_protocol):
            msg = f'Unsupported or invalid programmer protocol: {protocol!r}.'
            raise InvalidResponseError(msg)
    return protocol


def open_connection(port: str) -> IConnection:
    connection = IConnection(port)
    try:
        protocol = _detect_protocol(connection)
        return _CONNECTIONS[protocol](port, existing_connection=connection)
    except BaseException:
        connection.close()
        raise
