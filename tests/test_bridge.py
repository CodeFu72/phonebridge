import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
import dbus
from bridge import Bridge

class BluetoothWorkerTests(unittest.TestCase):
    def worker(self):
        worker = Bridge.__new__(Bridge)
        worker.emit = Mock()
        worker.access = Mock()
        worker.bus = Mock()
        worker.session = '/session'
        worker.events = Mock()
        return worker

    def test_send_reuses_session_and_submits_exactly_once_with_private_file(self):
        worker = self.worker()
        def submit(filename, folder, options, **kwargs):
            path = Path(filename)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
            self.assertIn(b'TEL:+15551234567', path.read_bytes())
            self.assertEqual(folder, 'outbox')
            self.assertEqual(str(options['Charset']), 'utf8')
            self.assertFalse(options['Retry'])
            return '/session/transfer1', {'Status': 'complete'}
        worker.access.PushMessage.side_effect = submit
        with patch('bridge.wait_transfer', return_value=True):
            worker.send({'id': 'test', 'address': '+15551234567', 'text': 'Example'})
        worker.access.PushMessage.assert_called_once()
        worker.bus.get_object.assert_not_called()
        worker.emit.assert_called_once_with('sent', {'id': 'test', 'state': 'accepted', 'detail': 'Accepted by iPhone; delivery not confirmed.'})
        filename = worker.access.PushMessage.call_args.args[0]
        self.assertFalse(Path(filename).exists())

    def test_submission_error_is_uncertain_and_never_retried(self):
        worker = self.worker()
        worker.access.PushMessage.side_effect = dbus.DBusException('private remote detail', name='org.bluez.obex.Error.Failed')
        worker.send({'id': 'test', 'address': '+15551234567', 'text': 'Example'})
        worker.access.PushMessage.assert_called_once()
        event, result = worker.emit.call_args.args
        self.assertEqual(result['state'], 'uncertain')
        self.assertNotIn('private', result['detail'])

    def test_invalid_recipient_is_not_submitted(self):
        worker = self.worker()
        worker.send({'id': 'test', 'address': 'Wrong Name', 'text': 'Example'})
        worker.access.PushMessage.assert_not_called()
        self.assertIn('did not start', worker.emit.call_args.args[1]['detail'])
