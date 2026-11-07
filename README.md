# json_pointer_lib

Resolve and apply RFC 6901 JSON Pointers against plain Python JSON values.

```python
from json_pointer_lib import resolve, apply

doc = {"foo": ["bar", "baz"], "a/b": 1}

resolve(doc, "/foo/0")          # 'bar'
resolve(doc, "/a~1b")           # 1
apply(doc, "/foo/1", "qux")     # {'foo': ['bar', 'qux'], 'a/b': 1}
```

The exported names are:

- `escape(token)` / `unescape(token)` — encode and decode `~` and `/` in a reference token.
- `parse(pointer)` — split a pointer string into a list of unescaped tokens.
- `resolve(document, pointer)` — return the value the pointer addresses.
- `apply(document, pointer, value)` — return a copy of the document with `value` placed at the pointer.
- `JSONPointerError`, `InvalidPointerError`, `ResolutionError` — the exception hierarchy.

## Why this exists

Python's standard library has no JSON Pointer implementation, and pulling in a
JSON library just for pointer handling is usually overkill.  This module is a
small, dependency-free layer that works on whatever `json.loads` already
produced: dicts, lists, strings, numbers, booleans and `None`.

The main trade-off is in `apply`.  Rather than mutating the input document in
place, `apply` returns a new document and shallow-copies only the containers
along the path to the target.  That keeps callers from accidentally sharing
state, at the cost of a little copying.  Sibling values are shared by
reference, so `apply` is cheap when the document is large but the path is
short.

## The awkward edge

`~01` is not `/`.  The RFC 6901 escape rules are applied in a single pass,
so `~0` becomes `~` and `~1` becomes `/`, but the two substitutions cannot be
chained.  `unescape("~01")` returns `"~1"`, not `"/"`.  Code that does
`token.replace("~1", "/").replace("~0", "~")` gets this wrong.  This
library scans the token once and rejects malformed escapes such as `~2` or a
trailing `~` with `InvalidPointerError`.

Array indices are also strict: `01` is not a valid index, and neither is
`-1`.  `resolve(doc, "/arr/01")` raises `ResolutionError` even if the array
has more than two elements.

## Design notes

The window stores values eagerly rather than keeping running aggregates. Running
sums drift with floating point over long streams, and recomputing from a small
buffer is cheap enough that the drift is not worth the speed.

