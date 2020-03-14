from LSP.plugin.core.bidict import BidirectionalDictionary
from unittest import TestCase


class TestBidirectionalDictionary(TestCase):

    def test_insertion(self):
        d = BidirectionalDictionary()
        d["foo"] = "bar"
        self.assertIn("bar", d._inverse)
        self.assertIn("foo", d)

    def test_removal(self):
        d = BidirectionalDictionary()
        d["foo"] = "bar"
        d["qux"] = "asdf"
        self.assertEqual(len(d), 2)
        d.pop("foo")
        self.assertEqual(len(d), 1)
        self.assertNotIn("foo", d)
        self.assertIn("qux", d)
        self.assertIn("asdf", d._inverse)
        self.assertNotIn("bar", d._inverse)
