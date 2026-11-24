import unittest
from send_test import MAX_TEXT_BYTES, make_bmessage, recipient_field, wait_transfer, push_options, TransferEvents
from unittest.mock import Mock

class SendTests(unittest.TestCase):
    def test_completion_event_survives_transfer_removal(self):
        tracker = TransferEvents('/session')
        tracker.changed('org.bluez.obex.Transfer1', {'Status': 'complete'}, [], path='/session/transfer1')
        tracker.changed('org.bluez.obex.Transfer1', {'Status': 'active'}, [], path='/session/transfer1')
        tracker.changed('org.bluez.obex.Transfer1', {'Status': 'error'}, [], path='/other/transfer1')
        bus = Mock()
        self.assertTrue(wait_transfer(bus, '/session/transfer1', {'Status': 'active'}, tracker))
        bus.get_object.assert_not_called()
        self.assertNotIn('/other/transfer1', tracker.statuses)

    def test_unknown_object_is_not_success(self):
        import dbus
        from unittest.mock import patch
        bus = Mock()
        error = dbus.DBusException('Gone', name='org.freedesktop.DBus.Error.UnknownObject')
        with patch('send_test.dbus.Interface', side_effect=error), patch('send_test.time.sleep'), patch('send_test.time.monotonic', side_effect=[0, 0, 0, 2, 2]):
            self.assertIsNone(wait_transfer(bus, '/gone', {'Status': 'active'}))

    def test_bluez_charset_and_retry_options(self):
        options = push_options()
        self.assertEqual(options['Charset'].lower(), 'utf8')
        self.assertFalse(options['Retry'])
        self.assertIn(b'CHARSET:UTF-8\r\n', make_bmessage('+15551234567', 'Test'))

    def test_recipient_injection_and_multiple_recipients_rejected(self):
        for address in ['Contact Name', '+15551234567\r\nEND:VCARD', 'a@example.com,b@example.com', 'a@example.com\nTEL:+15551234567']:
            with self.assertRaises(ValueError):
                recipient_field(address)

    def test_utf8_length_and_single_recipient(self):
        payload = make_bmessage('+15551234567', 'Test 🙂').decode('utf-8')
        block = payload[payload.index('BEGIN:MSG\r\n'):payload.index('END:BBODY')]
        self.assertIn('LENGTH:'+str(len(block.encode('utf-8')))+'\r\n', payload)
        self.assertEqual(payload.count('TEL:'), 1)
        self.assertEqual(payload.count('BEGIN:BENV'), 1)
        self.assertIn('VERSION:1.4\r\n', payload)

    def test_line_breaks_sent_as_crlf(self):
        payload = make_bmessage('+15551234567', 'Hi\nsecond line\r\nthird').decode('utf-8')
        self.assertIn('BEGIN:MSG\r\nHi\r\nsecond line\r\nthird\r\nEND:MSG\r\n', payload)
        block = payload[payload.index('BEGIN:MSG\r\n'):payload.index('END:BBODY')]
        self.assertIn('LENGTH:'+str(len(block.encode('utf-8')))+'\r\n', payload)

    def test_structural_body_and_controls_rejected(self):
        for text in ['END:MSG', 'line\nEND:MSG', 'a\nbegin:vcard', '\x00', 'tab\x07', '', 'x'*(MAX_TEXT_BYTES+1)]:
            with self.assertRaises(ValueError):
                make_bmessage('+15551234567', text)
        self.assertEqual(recipient_field('person@example.com'), 'EMAIL')

    def test_transfer_initial_complete_or_error_needs_no_poll_or_resend(self):
        bus = Mock()
        self.assertTrue(wait_transfer(bus, '/transfer', {'Status': 'complete'}))
        self.assertFalse(wait_transfer(bus, '/transfer', {'Status': 'error'}))
        bus.get_object.assert_not_called()

    def test_polled_completion_is_not_undone_by_an_older_signal(self):
        # Neon review #1: an earlier 'active' signal must not overwrite a polled 'complete'.
        from unittest.mock import patch
        tracker = TransferEvents('/session')
        tracker.changed('org.bluez.obex.Transfer1', {'Status': 'active'}, [], path='/session/t1')
        properties = Mock(); properties.Get.return_value = 'complete'
        with patch('send_test.dbus.Interface', return_value=properties), patch('send_test.time.sleep'):
            self.assertTrue(wait_transfer(Mock(), '/session/t1', {'Status': 'active'}, tracker))
        properties.Get.assert_called_once()
