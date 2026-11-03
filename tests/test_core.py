"""Tests for json_pointer_lib.core.

Run with::

    PYTHONPATH=src python -m unittest discover -s tests
"""

import unittest

from json_pointer_lib import (
    InvalidPointerError,
    ResolutionError,
    apply,
    escape,
    parse,
    resolve,
    unescape,
)


class TestEscape(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(escape("foo"), "foo")

    def test_tilde(self):
        self.assertEqual(escape("a~b"), "a~0b")

    def test_slash(self):
        self.assertEqual(escape("a/b"), "a~1b")

    def test_both(self):
        # Order matters: ~ must be escaped before /.
        self.assertEqual(escape("~/~"), "~0~1~0")

    def test_round_trip(self):
        for token in ["", "~", "/", "~/", "/~", "a~0b", "m~n"]:
            self.assertEqual(unescape(escape(token)), token)


class TestUnescape(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(unescape("foo"), "foo")

    def test_tilde_zero(self):
        self.assertEqual(unescape("a~0b"), "a~b")

    def test_tilde_one(self):
        self.assertEqual(unescape("a~1b"), "a/b")

    def test_tilde_zero_one(self):
        # ~01 -> ~1, not /.
        self.assertEqual(unescape("~01"), "~1")

    def test_bad_escape(self):
        with self.assertRaises(InvalidPointerError):
            unescape("a~2b")

    def test_dangling_tilde(self):
        with self.assertRaises(InvalidPointerError):
            unescape("a~")


class TestParse(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(parse(""), [])

    def test_root_slash(self):
        self.assertEqual(parse("/"), [""])

    def test_simple(self):
        self.assertEqual(parse("/foo/bar"), ["foo", "bar"])

    def test_escaped(self):
        self.assertEqual(parse("/a~1b/c~0d"), ["a/b", "c~d"])

    def test_missing_leading_slash(self):
        with self.assertRaises(InvalidPointerError):
            parse("foo")

    def test_trailing_slash(self):
        self.assertEqual(parse("/foo/"), ["foo", ""])

    def test_non_string(self):
        with self.assertRaises(InvalidPointerError):
            parse(123)  # type: ignore[arg-type]


class TestResolve(unittest.TestCase):
    def setUp(self):
        self.doc = {
            "foo": ["bar", "baz"],
            "": 0,
            "a/b": 1,
            "c%d": 2,
            "e^f": 3,
            "g|h": 4,
            "i\\j": 5,
            "k\"l": 6,
            " ": 7,
            "m~n": 8,
        }

    def test_whole_document(self):
        self.assertIs(resolve(self.doc, ""), self.doc)

    def test_object_member(self):
        self.assertEqual(resolve(self.doc, "/foo"), ["bar", "baz"])

    def test_array_index(self):
        self.assertEqual(resolve(self.doc, "/foo/0"), "bar")
        self.assertEqual(resolve(self.doc, "/foo/1"), "baz")

    def test_empty_key(self):
        self.assertEqual(resolve(self.doc, "/"), 0)

    def test_escaped_slash_key(self):
        self.assertEqual(resolve(self.doc, "/a~1b"), 1)

    def test_escaped_tilde_key(self):
        self.assertEqual(resolve(self.doc, "/m~0n"), 8)

    def test_missing_key(self):
        with self.assertRaises(ResolutionError):
            resolve(self.doc, "/nope")

    def test_index_out_of_range(self):
        with self.assertRaises(ResolutionError):
            resolve(self.doc, "/foo/2")

    def test_non_index_token(self):
        with self.assertRaises(ResolutionError):
            resolve(self.doc, "/foo/bar")

    def test_descend_into_scalar(self):
        with self.assertRaises(ResolutionError):
            resolve(self.doc, "/foo/0/x")

    def test_leading_zero_is_not_a_valid_index(self):
        with self.assertRaises(ResolutionError):
            resolve(self.doc, "/foo/01")


class TestApply(unittest.TestCase):
    def test_replace_object_member(self):
        doc = {"a": 1, "b": 2}
        out = apply(doc, "/a", 99)
        self.assertEqual(out, {"a": 99, "b": 2})
        # Original untouched.
        self.assertEqual(doc, {"a": 1, "b": 2})

    def test_replace_array_element(self):
        doc = {"a": [1, 2, 3]}
        out = apply(doc, "/a/1", 99)
        self.assertEqual(out, {"a": [1, 99, 3]})
        self.assertEqual(doc, {"a": [1, 2, 3]})

    def test_replace_root(self):
        doc = {"a": 1}
        out = apply(doc, "", {"b": 2})
        self.assertEqual(out, {"b": 2})
        self.assertEqual(doc, {"a": 1})

    def test_add_new_key(self):
        doc = {"a": 1}
        out = apply(doc, "/b", 2)
        self.assertEqual(out, {"a": 1, "b": 2})
        self.assertEqual(doc, {"a": 1})

    def test_empty_key(self):
        doc = {"": 1}
        out = apply(doc, "/", 2)
        self.assertEqual(out, {"": 2})

    def test_escaped_key(self):
        doc = {"a/b": 1}
        out = apply(doc, "/a~1b", 2)
        self.assertEqual(out, {"a/b": 2})

    def test_missing_parent(self):
        doc = {"a": 1}
        with self.assertRaises(ResolutionError):
            apply(doc, "/x/y", 2)

    def test_index_out_of_range(self):
        doc = {"a": [1]}
        with self.assertRaises(ResolutionError):
            apply(doc, "/a/5", 2)

    def test_non_index_on_array(self):
        doc = {"a": [1]}
        with self.assertRaises(ResolutionError):
            apply(doc, "/a/x", 2)

    def test_invalid_pointer(self):
        doc = {"a": 1}
        with self.assertRaises(InvalidPointerError):
            apply(doc, "a", 2)

    def test_does_not_mutate_nested_siblings(self):
        shared = {"x": 1}
        doc = {"a": shared, "b": shared}
        out = apply(doc, "/a/x", 2)
        # We shallow-copy along the path, so /a is a new dict but /b still
        # points at the original shared object.
        self.assertEqual(out["a"], {"x": 2})
        self.assertIs(out["b"], shared)
        self.assertEqual(shared, {"x": 1})


if __name__ == "__main__":
    unittest.main()
