"""Core implementation of RFC 6901 JSON Pointers.

A JSON Pointer is a string syntax for identifying a specific value within a
JSON document.  The empty string points at the whole document; otherwise the
pointer is a sequence of reference tokens separated by ``/``.

Design notes:

* We deliberately do **not** mutate the input document when applying a
  pointer.  ``apply`` returns a new document.  This makes the function safe
  to call in functional pipelines and avoids surprising callers who still
  hold a reference to the original data.
* ``~0`` and ``~1`` are unescaped in a single left-to-right pass.  Doing the
  substitutions with ``str.replace`` in sequence would be wrong: replacing
  ``~1`` first and then ``~0`` would turn ``~01`` into ``/`` (correct is
  ``~1``).  The single pass below is the only correct order-independent
  approach.
* The pointer grammar is strict.  A non-empty pointer must start with ``/``.
  Tokens are the text between slashes; the empty token is legal and refers
  to the key ``""``.
"""

from __future__ import annotations

from typing import Any, List, Union

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


class JSONPointerError(Exception):
    """Base class for all errors raised by this module."""


class InvalidPointerError(JSONPointerError):
    """Raised when a pointer string is not valid RFC 6901 syntax."""


class ResolutionError(JSONPointerError):
    """Raised when a valid pointer cannot be resolved against a document."""


# A JSON document, as far as this library is concerned, is any combination of
# dicts, lists, strings, numbers, booleans and None.  We keep the alias loose
# so callers can pass whatever their parser produced.
JSONValue = Union[dict, list, str, int, float, bool, None]


def _unescape_token(token: str) -> str:
    """Return *token* with ``~1`` -> ``/`` and ``~0`` -> ``~`` applied.

    The scan is a single pass so that the order of substitutions cannot
    change the result.  ``~01`` must become ``~1``, not ``/``.
    """
    out: List[str] = []
    i = 0
    n = len(token)
    while i < n:
        ch = token[i]
        if ch == "~" and i + 1 < n:
            nxt = token[i + 1]
            if nxt == "0":
                out.append("~")
                i += 2
                continue
            if nxt == "1":
                out.append("/")
                i += 2
                continue
            # A bare ~ followed by anything else is not a valid escape.
            raise InvalidPointerError(
                f"invalid escape sequence '~{nxt}' at offset {i} in token {token!r}"
            )
        if ch == "~":
            # Trailing ~ with nothing after it.
            raise InvalidPointerError(
                f"dangling '~' at offset {i} in token {token!r}"
            )
        out.append(ch)
        i += 1
    return "".join(out)


def escape(token: str) -> str:
    """Escape *token* for use as a reference token in a pointer.

    ``~`` becomes ``~0`` and ``/`` becomes ``~1``.  The order matters: ``~``
    must be replaced first, otherwise ``/`` would be turned into ``~1`` and
    then the ``~`` inside that would be doubled.
    """
    return token.replace("~", "~0").replace("/", "~1")


def unescape(token: str) -> str:
    """Inverse of :func:`escape`.

    Raises :class:`InvalidPointerError` for malformed escapes.  Keeping this
    strict means callers get an early signal instead of silently receiving a
    token that will not match any key.
    """
    return _unescape_token(token)


def parse(pointer: str) -> List[str]:
    """Parse *pointer* into a list of unescaped reference tokens.

    The empty string parses to ``[]``.  Any other string must begin with
    ``/``.  A trailing ``/`` yields a final empty token, which is a valid
    key (the empty string).
    """
    if not isinstance(pointer, str):
        raise InvalidPointerError(f"pointer must be a string, got {type(pointer).__name__}")
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise InvalidPointerError(f"pointer must be empty or start with '/', got {pointer!r}")
    raw_tokens = pointer.split("/")[1:]
    return [_unescape_token(tok) for tok in raw_tokens]


def _is_index(token: str) -> bool:
    """True if *token* is a valid array index per RFC 6901.

    RFC 6901 says array indices are either ``0`` or a non-zero digit
    followed by digits.  This rules out ``01``, ``+1``, ``-1``, ``1.0``.
    """
    if token == "0":
        return True
    if not token:
        return False
    if token[0] == "0":
        return False
    return token.isdigit()


def resolve(document: JSONValue, pointer: str) -> JSONValue:
    """Return the value inside *document* addressed by *pointer*.

    Raises :class:`InvalidPointerError` if the pointer syntax is bad and
    :class:`ResolutionError` if the pointer does not match the document.
    """
    tokens = parse(pointer)
    current: Any = document
    for index, token in enumerate(tokens):
        if isinstance(current, dict):
            if token not in current:
                raise ResolutionError(
                    f"key {token!r} not found at token {index} of {pointer!r}"
                )
            current = current[token]
        elif isinstance(current, list):
            if not _is_index(token):
                raise ResolutionError(
                    f"token {token!r} at index {index} is not a valid array index"
                )
            idx = int(token)
            if idx >= len(current):
                raise ResolutionError(
                    f"array index {idx} out of range at token {index} of {pointer!r}"
                )
            current = current[idx]
        else:
            raise ResolutionError(
                f"cannot descend into {type(current).__name__} at token {index} of {pointer!r}"
            )
    return current


def _set(document: JSONValue, tokens: List[str], value: JSONValue, pointer: str) -> JSONValue:
    """Return a copy of *document* with *value* placed at *tokens*.

    The parent containers along the path are shallow-copied so the caller's
    original document is not modified.  The final container is updated in
    place on that copy.
    """
    if not tokens:
        return value

    # Walk down to the parent of the final token, copying as we go.
    path: List[Any] = []
    current: Any = document
    for index, token in enumerate(tokens[:-1]):
        path.append((current, token))
        if isinstance(current, dict):
            if token not in current:
                raise ResolutionError(
                    f"key {token!r} not found at token {index} of {pointer!r}"
                )
            current = current[token]
        elif isinstance(current, list):
            if not _is_index(token):
                raise ResolutionError(
                    f"token {token!r} at index {index} is not a valid array index"
                )
            idx = int(token)
            if idx >= len(current):
                raise ResolutionError(
                    f"array index {idx} out of range at token {index} of {pointer!r}"
                )
            current = current[idx]
        else:
            raise ResolutionError(
                f"cannot descend into {type(current).__name__} at token {index} of {pointer!r}"
            )

    final = tokens[-1]
    if isinstance(current, dict):
        new_container = dict(current)
        new_container[final] = value
    elif isinstance(current, list):
        if not _is_index(final):
            raise ResolutionError(
                f"token {final!r} is not a valid array index for assignment"
            )
        idx = int(final)
        if idx >= len(current):
            raise ResolutionError(
                f"array index {idx} out of range for assignment"
            )
        new_container = list(current)
        new_container[idx] = value
    else:
        raise ResolutionError(
            f"cannot assign into {type(current).__name__}"
        )

    # Rebuild the path from the bottom up, replacing each child with the
    # copied-and-updated version.
    result: Any = new_container
    for parent, token in reversed(path):
        if isinstance(parent, dict):
            new_parent = dict(parent)
            new_parent[token] = result
        elif isinstance(parent, list):
            idx = int(token)
            new_parent = list(parent)
            new_parent[idx] = result
        else:  # pragma: no cover - the walk above already rejected these
            raise ResolutionError(
                f"cannot assign into {type(parent).__name__}"
            )
        result = new_parent
    return result


def apply(document: JSONValue, pointer: str, value: JSONValue) -> JSONValue:
    """Return a copy of *document* with *value* placed at *pointer*.

    The original document is never mutated.  The parent containers along the
    path are shallow-copied; sibling values are shared by reference.

    Raises :class:`InvalidPointerError` for bad pointer syntax and
    :class:`ResolutionError` when the path does not exist.
    """
    tokens = parse(pointer)
    return _set(document, tokens, value, pointer)
