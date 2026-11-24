import unittest
from unittest.mock import Mock, patch
import dbus
import connect_phone as setup

class SetupTests(unittest.TestCase):
    def test_selection_uses_list_number_and_zero_cancels(self):
        with patch('builtins.input', return_value='2'), patch('builtins.print'):
            self.assertEqual(setup.choose(['A', 'B'], 'Select'), 1)
        with patch('builtins.input', return_value='0'), patch('builtins.print'):
            self.assertIsNone(setup.choose(['A'], 'Select'))
        with patch('builtins.input', return_value='3'), patch('builtins.print'):
            with self.assertRaises(ValueError):
                setup.choose(['A'], 'Select')

    def test_confirmation_requires_explicit_yes(self):
        with patch('builtins.input', return_value='y'):
            self.assertFalse(setup.yes('Approve?'))
        with patch('builtins.input', return_value='yes'):
            self.assertTrue(setup.yes('Approve?'))

    def test_pairing_failure_restores_adapter_settings_and_unregisters_agent(self):
        bus, properties, manager, agent = Mock(), Mock(), Mock(), Mock()
        initial = {'Powered': True, 'Discoverable': False, 'Pairable': False, 'DiscoverableTimeout': 60}
        objects = {'/adapter': {setup.ADAPTER: initial}}
        def fail_pairable(interface, name, value, **kwargs):
            if name == 'Pairable' and bool(value):
                raise dbus.DBusException('Unavailable', name='org.bluez.Error.Failed')
        properties.Set.side_effect = fail_pairable
        with patch('connect_phone.dbus.Interface', side_effect=[properties, manager]), patch('connect_phone.PairingAgent', return_value=agent):
            with self.assertRaises(dbus.DBusException):
                setup.pair_phone(bus, objects)
        manager.RegisterAgent.assert_called_once()
        manager.UnregisterAgent.assert_called_once_with(setup.AGENT_PATH, timeout=5)
        agent.remove_from_connection.assert_called_once()
        restored = [(call.args[1], call.args[2]) for call in properties.Set.call_args_list][-3:]
        self.assertEqual(restored, [('Discoverable', False), ('Pairable', False), ('DiscoverableTimeout', 60)])

    def test_declining_power_on_changes_nothing(self):
        bus, properties = Mock(), Mock()
        objects = {'/adapter': {setup.ADAPTER: {'Powered': False}}}
        with patch('connect_phone.dbus.Interface', return_value=properties), patch('connect_phone.yes', return_value=False):
            self.assertIsNone(setup.pair_phone(bus, objects))
        properties.Set.assert_not_called()

    def test_agent_denies_unconfirmed_device_service(self):
        # No real bus/service registration is needed to exercise authorization.
        agent = Mock()
        agent.accepted_path = '/approved-phone'
        agent.reject.side_effect = dbus.DBusException('Rejected', name='org.bluez.Error.Rejected')
        with self.assertRaises(dbus.DBusException):
            setup.PairingAgent.AuthorizeService(agent, '/other-phone', 'service')
        agent.reject.assert_called_once()


class PairedSetupFlowTests(unittest.TestCase):
    def test_existing_phone_only_checks_capabilities_without_pairing(self):
        bus, manager = Mock(), Mock()
        objects = {'/adapter': {setup.ADAPTER: {'Powered': True}}, '/phone': {setup.DEVICE: {
            'Alias': 'Example phone', 'Paired': True, 'Address': '00:00:00:00:00:01',
            'Adapter': '/adapter', 'UUIDs': [setup.MAP]}}}
        manager.GetManagedObjects.return_value = objects
        with patch('connect_phone.dbus.SystemBus', return_value=bus), patch('connect_phone.dbus.Interface', return_value=manager), patch('connect_phone.Path.exists', return_value=True), patch('connect_phone.yes', return_value=True), patch('connect_phone.choose', return_value=0), patch('connect_phone.probe_map', return_value={'session_opened': True, 'message_access_methods': ['ListMessages']}) as probe, patch('connect_phone.pair_phone') as pair, patch('builtins.input', return_value=''), patch('builtins.print'):
            self.assertEqual(setup.main(), 0)
        probe.assert_called_once_with(setup.dbus, '00:00:00:00:00:01')
        pair.assert_not_called()
        manager.RemoveDevice.assert_not_called()
        manager.PushMessage.assert_not_called()
