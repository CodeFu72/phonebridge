#!/usr/bin/env python3
"""PhoneBridge feasibility probe. Does not fetch or send message content."""
import argparse
import json
import re
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

DEVICE = 'org.bluez.Device1'
ADAPTER = 'org.bluez.Adapter1'
MAP = '00001132-0000-1000-8000-00805f9b34fb'
ANCS = '7905f431-b5ce-4e99-a40f-4b1e122d00d0'
OBEX = 'org.bluez.obex'
MESSAGE_ACCESS = OBEX + '.MessageAccess1'


def devices_from(objects):
    return [(str(path), interfaces[DEVICE]) for path, interfaces in sorted(objects.items())
            if DEVICE in interfaces and interfaces[DEVICE].get('Paired', False)]


def capabilities(props):
    uuids = {str(u).lower() for u in props.get('UUIDs', [])}
    return {'paired': bool(props.get('Paired', False)),
            'connected': bool(props.get('Connected', False)),
            'services_resolved': bool(props.get('ServicesResolved', False)),
            'map_advertised': MAP in uuids, 'ancs_advertised': ANCS in uuids}


def method_names(xml):
    root = ET.fromstring(xml)
    return sorted(m.attrib['name'] for interface in root.findall('interface')
                  if interface.attrib.get('name') == MESSAGE_ACCESS
                  for m in interface.findall('method'))


def probe_map(dbus, address):
    """Open one MAP session, inspect methods/folders, and always close it."""
    bus = dbus.SessionBus()
    client = dbus.Interface(bus.get_object(OBEX, '/org/bluez/obex'), OBEX + '.Client1')
    session = client.CreateSession(address, dbus.Dictionary({'Target': 'map'}, signature='sv'), timeout=30)
    try:
        obj = bus.get_object(OBEX, session)
        xml = dbus.Interface(obj, 'org.freedesktop.DBus.Introspectable').Introspect(timeout=10)
        methods = method_names(str(xml))
        result = {'session_opened': True, 'message_access_methods': methods,
                  'push_method_exposed': 'PushMessage' in methods,
                  'receive_verified': False, 'send_verified': False}
        if 'ListFolders' in methods:
            folders = dbus.Interface(obj, MESSAGE_ACCESS).ListFolders(
                dbus.Dictionary({'MaxCount': dbus.UInt16(32)}, signature='sv'), timeout=20)
            result['root_folder_count'] = len(folders)
        return result
    finally:
        client.RemoveSession(session, timeout=10)



def dbus_error_help(name, message):
    # Keep diagnostic output useful without printing device addresses or paths.
    detail = re.sub(r"(?i)(?:[0-9a-f]{2}:){5}[0-9a-f]{2}", "[device]", message)
    detail = re.sub(r"/org/bluez/[^\s]+", "[Bluetooth object]", detail)
    if name in ('org.freedesktop.DBus.Error.AccessDenied', 'org.freedesktop.DBus.Error.NoServer'):
        hint = 'Run in your regular Omarchy terminal as your own user; the Bluetooth bus was inaccessible.'
    elif name.startswith('org.bluez.obex.'):
        hint = ('The Bluetooth messaging session failed. Pairing alone does not establish messaging access. '
                'Keep the iPhone unlocked and check its Bluetooth permissions. '
                'If the Mac is connected to this iPhone over Bluetooth, disconnect that link before retrying. '
                'Missing message permissions may require accessory setup; do not unpair yet.')
    elif name == 'org.freedesktop.DBus.Error.ServiceUnknown':
        hint = 'Check that bluez-obex is installed and that this terminal has access to your user session bus.'
    else:
        hint = 'The Bluetooth operation failed; use the error detail to choose the next diagnostic.'
    return detail, hint


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe', action='store_true', help='Select a paired phone and open a temporary MAP session')
    parser.add_argument('--report', type=Path, help='Save capability booleans only, excluding names, addresses and messages')
    args = parser.parse_args()
    try:
        import dbus
    except ImportError:
        print('Missing python-dbus. Install with: omarchy pkg add python-dbus', file=sys.stderr)
        return 2
    report = {'stage': 'capability_probe', 'receive_verified': False, 'send_verified': False,
              'obex_installed': Path('/usr/share/dbus-1/services/org.bluez.obex.service').exists()}
    try:
        bus = dbus.SystemBus()
        objects = dbus.Interface(bus.get_object('org.bluez', '/'),
                                 'org.freedesktop.DBus.ObjectManager').GetManagedObjects(timeout=10)
        adapters = [i[ADAPTER] for i in objects.values() if ADAPTER in i]
        report['adapter_count'] = len(adapters)
        report['adapter_powered'] = any(bool(a.get('Powered', False)) for a in adapters)
        devices = devices_from(objects)
        report['paired_device_count'] = len(devices)
        print('Bluetooth adapters:', len(adapters), '| Powered:', report['adapter_powered'])
        print('OBEX installed:', report['obex_installed'])
        for number, (_, props) in enumerate(devices, 1):
            # Device names are shown only interactively, never in saved reports.
            print(f"{number}. {props.get('Alias', 'Paired device')} | {json.dumps(capabilities(props))}")
        if not report['obex_installed']:
            print('MAP needs this package: omarchy pkg add bluez-obex')
        if args.probe:
            if not devices:
                raise ValueError('Pair your iPhone in Bluetooth settings first, then run this again.')
            if not report['obex_installed']:
                raise ValueError('Install bluez-obex before running --probe.')
            choice = int(input('Type the LIST NUMBER before your iPhone name (for example 2; 0 cancels): '))
            if choice == 0:
                return 0
            if not 1 <= choice <= len(devices):
                raise ValueError('That device number is not in the list.')
            props = devices[choice - 1][1]
            report['phone'] = capabilities(props)
            print('Opening temporary messaging session. Accept access on the iPhone if prompted.')
            report['map'] = probe_map(dbus, str(props['Address']))
            print(json.dumps(report['map'], indent=2))
            print('A successful probe does not prove receiving or sending. No messages were fetched or sent.')
    except (dbus.DBusException, OSError, ValueError, EOFError) as error:
        # D-Bus error messages may contain device identifiers; save only error names.
        name = error.get_dbus_name() if isinstance(error, dbus.DBusException) else type(error).__name__
        report['error'] = name
        if isinstance(error, dbus.DBusException):
            print('Bluetooth access failed:', name, file=sys.stderr)
            detail, hint = dbus_error_help(name, error.get_dbus_message())
            print('Detail:', detail, file=sys.stderr)
            print(hint, file=sys.stderr)
        else:
            print(str(error), file=sys.stderr)
        return 2
    finally:
        if args.report:
            # Create privately; refuse an existing file so symlinks cannot redirect writes.
            import os
            fd = os.open(args.report, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w') as stream:
                json.dump(report, stream, indent=2)
                stream.write('\n')
            print('Saved capability-only report:', args.report)
    return 0


if __name__ == '__main__':
    sys.exit(main())
