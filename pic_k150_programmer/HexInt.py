class HexInt(int):
    # @TODO WTH?
    """Behaves just like an integer, except its __repr__ in python yields a hex string."""

    def __repr__(self):
        if self >= 0:
            return hex(self)
        else:
            # Avoid "future" warning and ensure eval(repr(self)) == self
            return '-' + hex(-self)

    def maybe_hex_int(value):
        if isinstance(value, int):
            return HexInt(value)
        else:
            return value

    maybe_hex_int = staticmethod(maybe_hex_int)

    _method_wrap = lambda super_method_name: lambda *args, **argd: HexInt.maybe_hex_int(int.__dict__[super_method_name](*args, **argd))

    __abs__ = _method_wrap('__abs__')
    __add__ = _method_wrap('__add__')
    __and__ = _method_wrap('__and__')
    __floordiv__ = _method_wrap('__floordiv__')
    __invert__ = _method_wrap('__invert__')
    __lshift__ = _method_wrap('__lshift__')
    __mod__ = _method_wrap('__mod__')
    __mul__ = _method_wrap('__mul__')
    __neg__ = _method_wrap('__neg__')
    __or__ = _method_wrap('__or__')
    __pos__ = _method_wrap('__pos__')
    __pow__ = _method_wrap('__pow__')
    __sub__ = _method_wrap('__sub__')
    __xor__ = _method_wrap('__xor__')
    __radd__ = _method_wrap('__add__')
    __rand__ = _method_wrap('__and__')
    __rfloordiv__ = _method_wrap('__floordiv__')
    __rmul__ = _method_wrap('__mul__')
    __ror__ = _method_wrap('__or__')
    __rsub__ = _method_wrap('__rsub__')
    __rxor__ = _method_wrap('__xor__')