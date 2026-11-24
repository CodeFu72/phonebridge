import unittest
from unittest.mock import Mock
import phonebridge as p

class ProbeTests(unittest.TestCase):
    def test_obex_failure_is_not_reported_as_a_sandbox_problem(self):
        detail, hint = p.dbus_error_help('org.bluez.obex.Error.Failed', 'Connection refused AA:BB:CC:DD:EE:FF')
        self.assertNotIn('AA:BB', detail)
        self.assertIn('Connection refused', detail)
        self.assertNotIn('bus was inaccessible', hint)
        _, denied_hint = p.dbus_error_help('org.freedesktop.DBus.Error.AccessDenied', 'Denied')
        self.assertIn('bus was inaccessible', denied_hint)

    def test_only_paired_devices_are_candidates(self):
        objects = {'/adapter': {p.ADAPTER: {}}, '/unpaired': {p.DEVICE: {'Paired': False}},
                   '/phone': {p.DEVICE: {'Paired': True, 'Alias': 'Private name'}}}
        self.assertEqual([path for path, _ in p.devices_from(objects)], ['/phone'])

    def test_capabilities_exclude_identifiers(self):
        props = {'Address': 'private', 'Alias': 'private', 'Paired': True, 'UUIDs': [p.MAP.upper()]}
        result = p.capabilities(props)
        self.assertTrue(result['map_advertised'])
        self.assertNotIn('private', str(result))
        self.assertFalse(result['ancs_advertised'])

    def test_session_closed_on_inspection_failure(self):
        dbus = Mock()
        client, introspection = Mock(), Mock()
        dbus.Interface.side_effect = [client, introspection]
        client.CreateSession.return_value = '/session'
        introspection.Introspect.side_effect = RuntimeError('Interrupted')
        with self.assertRaises(RuntimeError):
            p.probe_map(dbus, 'not-a-real-address')
        client.RemoveSession.assert_called_once_with('/session', timeout=10)
        client.PushMessage.assert_not_called()

    def test_send_capability_never_claims_send_verified(self):
        dbus = Mock()
        client, introspection, access = Mock(), Mock(), Mock()
        dbus.Interface.side_effect = [client, introspection, access]
        client.CreateSession.return_value = '/session'
        introspection.Introspect.return_value = f'<node><interface name="{p.MESSAGE_ACCESS}"><method name="PushMessage"/><method name="ListFolders"/></interface></node>'
        access.ListFolders.return_value = [{'Name': 'telecom'}]
        result = p.probe_map(dbus, 'not-a-real-address')
        self.assertTrue(result['push_method_exposed'])
        self.assertFalse(result['send_verified'])
        self.assertFalse(result['receive_verified'])
        self.assertEqual(result['root_folder_count'], 1)
        access.PushMessage.assert_not_called()
        access.ListMessages.assert_not_called()
        client.RemoveSession.assert_called_once()

if __name__ == '__main__':
    unittest.main()
