import json
from pathlib import Path
import tempfile
import unittest
from model import ClearedThreads, Message, conversation_order, contact_key


def message(key, address, when):
    return Message(key, address, 'Person', 'Private body', when)


class ThreadTests(unittest.TestCase):
    def test_newest_conversation_first(self):
        peers = {contact_key(a): (a, n) for a, n in [('+15550000001', 'A'), ('+15550000002', 'B'), ('+15550000003', 'C')]}
        texts = [message('1', '+15550000001', '20261020T120000'), message('2', '+15550000002', '20261021T120000')]
        self.assertEqual([v[1] for _, v in conversation_order(peers, texts)], ['B', 'A', 'C'])
        texts.append(message('3', '+15550000001', '20261021T130000'))
        self.assertEqual([v[1] for _, v in conversation_order(peers, texts)], ['A', 'B', 'C'])

    def test_deletion_persists_and_new_text_survives(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'cleared.json'
            state = ClearedThreads(path)
            old = message('1', '+15550000001', '20261020T120000')
            other = message('2', '+15550000002', '20261020T120000')
            state.clear(old.address, [old, other])
            restored = ClearedThreads(path)
            self.assertFalse(restored.visible(old))
            self.assertTrue(restored.visible(other))
            self.assertTrue(restored.visible(message('3', old.address, '20261021T120000')))
            self.assertTrue(restored.cleared('15550000001'))
            self.assertNotIn(old.address, path.read_text())
            self.assertNotIn(old.text, path.read_text())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_failed_save_keeps_state(self):
        from unittest.mock import patch
        state = ClearedThreads(memory_only=True)
        state.memory_only = False
        old = message('1', '+15550000001', '20261020T120000')
        with patch('model.write_private_json', side_effect=OSError('disk full')):
            with self.assertRaises(OSError): state.clear(old.address, [old])
        self.assertTrue(state.visible(old))
        self.assertFalse(state.cleared(old.address))

    def test_malformed_data_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'cleared.json'
            path.write_text(json.dumps({'messages': ['invalid']}))
            with self.assertRaises(ValueError): ClearedThreads(path)
