import unittest
from model import insert_emoji
from send_test import MAX_TEXT_BYTES

class EmojiTests(unittest.TestCase):
    def test_unicode_caret(self):
        self.assertEqual(insert_emoji('Hi 😊 friend', '❤️', 4), ('Hi 😊❤️ friend', 6))
    def test_selection(self):
        self.assertEqual(insert_emoji('Hello world', '👋', 11, (True, 6, 11)), ('Hello 👋', 7))
    def test_no_selection(self):
        self.assertEqual(insert_emoji('Hi', '😊', 1, (False, 0, 0)), ('H😊i', 2))
    def test_exact_limit(self):
        self.assertEqual(len(insert_emoji('a'*(MAX_TEXT_BYTES-4), '😊', -1)[0].encode()), MAX_TEXT_BYTES)
    def test_over_limit(self):
        with self.assertRaises(ValueError): insert_emoji('a'*(MAX_TEXT_BYTES-3), '😊', MAX_TEXT_BYTES-3)
    def test_replacement_budget(self):
        self.assertEqual(insert_emoji('a'*MAX_TEXT_BYTES, '❤️', MAX_TEXT_BYTES, (MAX_TEXT_BYTES-6, MAX_TEXT_BYTES)), ('a'*(MAX_TEXT_BYTES-6)+'❤️', MAX_TEXT_BYTES-4))
