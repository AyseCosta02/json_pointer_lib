"""RFC 6901 JSON Pointer resolution and application.

Exports the public API for this package.  Everything here is re-exported
from :mod:`json_pointer_lib.core` so that callers can simply do::

    from json_pointer_lib import resolve, apply

"""
from .core import (
    JSONPointerError,
    InvalidPointerError,
    ResolutionError,
    escape,
    unescape,
    parse,
    resolve,
    apply,
)

__all__ = [
    "JSONPointerError",
    "InvalidPointerError",
    "ResolutionError",
    "escape",
    "unescape",
    "parse",
    "resolve",
    "apply",
]
