import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from model import Favorites, SendGate, from_map

class DesktopStateTests(unittest.TestCase):
    def test_uncertain_send_cannot_be_repeated_without_acknowledgement(self):
        gate = SendGate(); gate.begin()
        with self.assertRaises(ValueError):
            gate.begin()
        gate.finish('uncertain')
        with self.assertRaises(ValueError):
            gate.begin()
        gate.acknowledge(); gate.begin(); gate.finish('accepted')
        self.assertEqual(gate.state, 'idle')

    def test_favorites_save_only_explicit_addresses_and_are_private(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'private/favorites.json'
            favorites = Favorites(path)
            favorites.toggle('+15551234567', 'Example')
            self.assertEqual(json.loads(path.read_text()), {'+15551234567': 'Example'})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
            favorites.toggle('+15551234567', 'Example')
            self.assertEqual(Favorites(path).items, {})

    def test_failed_favorite_save_preserves_previous_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'favorites.json'
            favorites = Favorites(path); favorites.toggle('+15551234567', 'Existing')
            before = path.read_bytes()
            with patch('model.os.replace', side_effect=OSError('disk unavailable')):
                with self.assertRaises(OSError):
                    favorites.toggle('+15557654321', 'New')
            self.assertEqual(path.read_bytes(), before)
            self.assertNotIn('+15557654321', favorites.items)
            self.assertEqual(list(path.parent.glob('.favorites-*')), [])

    def test_reconnect_session_path_does_not_duplicate_same_message_handle(self):
        props = {'SenderAddress': '+15551234567', 'Subject': '<not markup>', 'Sender': 'Example'}
        first = from_map('/session1/message123', props)
        second = from_map('/session2/message123', props)
        self.assertEqual(first.key, second.key)
        self.assertEqual(first.text, '<not markup>')
