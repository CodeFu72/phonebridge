#!/usr/bin/env python3
"""Guided local Bluetooth pairing/permission check. Never reads or sends texts."""
import signal
from pathlib import Path
import sys
import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib, GLibUnix
from phonebridge import ADAPTER, DEVICE, MAP, capabilities, devices_from, probe_map, dbus_error_help

AGENT = 'org.bluez.Agent1'
AGENT_PATH = '/org/phonebridge/pairing_agent'


def yes(prompt):
    return input(prompt+' [type yes to confirm]: ').strip().lower() == 'yes'


def choose(options, prompt):
    for number, name in enumerate(options, 1):
        print(f'{number}. {name}')
    number = int(input(prompt))
    if number == 0:
        return None
    if not 1 <= number <= len(options):
        raise ValueError('That list number is not available.')
    return number-1


class PairingAgent(dbus.service.Object):
    def __init__(self, bus, path):
        super().__init__(bus, path)
        self.bus = bus
        self.accepted_path = None

    def reject(self):
        raise dbus.DBusException('User did not approve this pairing request.', name='org.bluez.Error.Rejected')

    def name(self, device):
        props = dbus.Interface(self.bus.get_object('org.bluez', device), 'org.freedesktop.DBus.Properties')
        return str(props.Get(DEVICE, 'Alias', timeout=5))

    @dbus.service.method(AGENT, in_signature='ou', out_signature='')
    def RequestConfirmation(self, device, passkey):
        if self.accepted_path and self.accepted_path != str(device):
            self.reject()
        print(f'\nPairing with {self.name(device)}. Code: {int(passkey):06d}', flush=True)
        print('Compare this code with your iPhone. Keep both screens visible.', flush=True)
        if not yes('Do the codes match on YOUR iPhone?'):
            self.reject()
        self.accepted_path = str(device)
        print('Now tap Pair on the iPhone promptly.', flush=True)

    @dbus.service.method(AGENT, in_signature='o', out_signature='')
    def RequestAuthorization(self, device):
        if str(device) != self.accepted_path:
            self.reject()

    @dbus.service.method(AGENT, in_signature='os', out_signature='')
    def AuthorizeService(self, device, uuid):
        if str(device) != self.accepted_path:
            self.reject()
        print('The phone is requesting a Bluetooth service:', uuid, flush=True)
        if not yes('Allow this service from the iPhone you just paired?'):
            self.reject()

    @dbus.service.method(AGENT, in_signature='o', out_signature='s')
    def RequestPinCode(self, device):
        self.reject()

    @dbus.service.method(AGENT, in_signature='o', out_signature='u')
    def RequestPasskey(self, device):
        self.reject()

    @dbus.service.method(AGENT, in_signature='', out_signature='')
    def Cancel(self):
        print('\nThe pairing request expired or was canceled. If you retry, compare and confirm the new code.', flush=True)
        self.accepted_path = None

    @dbus.service.method(AGENT, in_signature='', out_signature='')
    def Release(self):
        pass


def pair_phone(bus, objects):
    adapters = [(str(path), interfaces[ADAPTER]) for path, interfaces in sorted(objects.items()) if ADAPTER in interfaces]
    if not adapters:
        raise ValueError('No Bluetooth adapter found. Check your adapter and Bluetooth service.')
    selected = 0
    if len(adapters) > 1:
        selected = choose([str(p.get('Alias', 'Bluetooth adapter')) for _, p in adapters], 'Choose adapter LIST NUMBER (0 cancels): ')
        if selected is None:
            return None
    path, state = adapters[selected]
    properties = dbus.Interface(bus.get_object('org.bluez', path), 'org.freedesktop.DBus.Properties')
    if not state.get('Powered', False):
        if not yes('Bluetooth is off. Turn it on?'):
            return None
        properties.Set(ADAPTER, 'Powered', dbus.Boolean(True), timeout=10)
    original = {key: state[key] for key in ('Discoverable', 'Pairable', 'DiscoverableTimeout') if key in state}
    manager = dbus.Interface(bus.get_object('org.bluez', '/org/bluez'), 'org.bluez.AgentManager1')
    agent = PairingAgent(bus, AGENT_PATH)
    registered = False
    loop = GLib.MainLoop()
    found = []
    sources = []
    try:
        manager.RegisterAgent(AGENT_PATH, 'KeyboardDisplay', timeout=10)
        registered = True
        manager.RequestDefaultAgent(AGENT_PATH, timeout=10)
        properties.Set(ADAPTER, 'DiscoverableTimeout', dbus.UInt32(180), timeout=10)
        properties.Set(ADAPTER, 'Pairable', dbus.Boolean(True), timeout=10)
        properties.Set(ADAPTER, 'Discoverable', dbus.Boolean(True), timeout=10)
        computer_name = str(properties.Get(ADAPTER, 'Alias', timeout=5))
        print('\nOn iPhone, open Settings > Bluetooth.', flush=True)
        print('Under Other Devices, tap this computer: '+computer_name, flush=True)
        print('Return here to confirm the matching six-digit code, then tap Pair on iPhone.', flush=True)
        print('Waiting up to three minutes. Ctrl+C cancels.', flush=True)
        def inspect():
            if agent.accepted_path:
                try:
                    device_props = dbus.Interface(bus.get_object('org.bluez', agent.accepted_path), 'org.freedesktop.DBus.Properties')
                    phone = device_props.GetAll(DEVICE, timeout=5)
                    if phone.get('Paired', False):
                        found.append(phone)
                        loop.quit()
                except dbus.DBusException:
                    pass
            return True
        sources.append(GLib.timeout_add_seconds(1, inspect))
        sources.append(GLib.timeout_add_seconds(180, lambda: (loop.quit(), True)[1]))
        for sig in (signal.SIGINT, signal.SIGTERM):
            sources.append(GLibUnix.signal_add(GLib.PRIORITY_DEFAULT, sig, lambda: (loop.quit(), True)[1]))
        loop.run()
        if not found:
            print('Pairing was not confirmed. No device was forgotten or automatically retried.')
            return None
        print('Pairing confirmed. Temporary discoverability is being restored.')
        return found[0]
    finally:
        for source in sources:
            GLib.source_remove(source)
        if registered:
            try:
                manager.UnregisterAgent(AGENT_PATH, timeout=5)
            except dbus.DBusException:
                pass
        # Restore these temporary settings even when pairing/advertising fails.
        for key in ('Discoverable', 'Pairable', 'DiscoverableTimeout'):
            if key in original:
                try:
                    properties.Set(ADAPTER, key, original[key], timeout=5)
                except dbus.DBusException:
                    print('Could not restore Bluetooth setting '+key+'. Check your Bluetooth settings.')
        agent.remove_from_connection()


def main():
    DBusGMainLoop(set_as_default=True)
    print('PhoneBridge — Connect your iPhone\n')
    print('This guide can pair a phone and check messaging access. It never reads or sends texts.')
    print('Disconnect PhoneBridge in its main window and close other MAP test tools before continuing.')
    if not yes('Ready to continue?'):
        return 0
    try:
        if not Path('/usr/share/dbus-1/services/org.bluez.obex.service').exists():
            raise ValueError('Missing bluez-obex. On Omarchy run: omarchy pkg add bluez-obex')
        bus = dbus.SystemBus()
        objects = dbus.Interface(bus.get_object('org.bluez', '/'), 'org.freedesktop.DBus.ObjectManager').GetManagedObjects(timeout=10)
        # Every paired device: a new iPhone may not advertise messaging (MAP) until its
        # permission switch is on, which is exactly what this setup helps with.
        phones = list(devices_from(objects))
        ready = lambda p: MAP in {str(u).lower() for u in p.get('UUIDs', [])}
        print('\nChoose an already paired phone, or pair a new one:')
        options = [str(p.get('Alias', 'Paired device'))+(' (messaging ready)' if ready(p) else '') for _, p in phones]+['Pair a new iPhone']
        index = choose(options, 'Type the LIST NUMBER (0 cancels): ')
        if index is None:
            return 0
        phone = phones[index][1] if index < len(phones) else pair_phone(bus, objects)
        if phone is None:
            return 1
        adapter_path = str(phone['Adapter'])
        adapter_state = objects.get(adapter_path, {}).get(ADAPTER, {})
        if not adapter_state.get('Powered', False):
            adapter_props = dbus.Interface(bus.get_object('org.bluez', adapter_path), 'org.freedesktop.DBus.Properties')
            if not bool(adapter_props.Get(ADAPTER, 'Powered', timeout=5)):
                if not yes('Bluetooth is off. Turn it on?'):
                    return 0
                adapter_props.Set(ADAPTER, 'Powered', dbus.Boolean(True), timeout=10)
        print('\nOn iPhone: Settings > Bluetooth > (i) beside this computer.')
        print('Enable Show Message Notifications if available. Leave your iPhone nearby and unlocked for setup.')
        input('Press Enter to check messaging access… ')
        try:
            result = probe_map(dbus, str(phone['Address']))
        except dbus.DBusException as error:
            detail, _ = dbus_error_help(error.get_dbus_name(), error.get_dbus_message())
            print('Messaging access not confirmed:', detail)
            if not yes('Run the temporary accessory signal to help reveal the permission switch?'):
                return 2
            import request_access
            if request_access.main(selected=phone) != 0:
                return 2
            input('After enabling Show Message Notifications, press Enter to check again… ')
            result = probe_map(dbus, str(phone['Address']))
        if not result.get('session_opened') or 'ListMessages' not in result.get('message_access_methods', []):
            raise ValueError('The phone did not expose the expected messaging operations.')
        print('\nCONNECTED: messaging access verified. No text was read or sent.')
        print('Open PhoneBridge, click Refresh, select your phone, then Connect.')
        print('First receive a fresh test text; send only after reviewing the recipient and message.')
        print('Setup does not establish recipient delivery or whether a send uses iMessage or SMS.')
        return 0
    except dbus.DBusException as error:
        detail, hint = dbus_error_help(error.get_dbus_name(), error.get_dbus_message())
        print('Connection setup did not complete:', detail, '\n'+hint)
        return 2
    except (OSError, ValueError, EOFError) as error:
        print('Setup stopped:', str(error))
        return 2
    except KeyboardInterrupt:
        print('\nSetup canceled. No text sent.')
        return 130

if __name__ == '__main__':
    result = main()
    if '--hold' in sys.argv:
        try:
            input('Press Enter to close the connection guide… ')
        except (EOFError, KeyboardInterrupt):
            pass
    sys.exit(result)
