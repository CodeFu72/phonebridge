#!/usr/bin/env python3
"""Wait for fresh inbox messages. No outgoing messages or disk history."""
import argparse
import sys
import time
import dbus
from phonebridge import OBEX, MESSAGE_ACCESS, devices_from, dbus_error_help

class FreshMessages:
    def __init__(self, initial):
        self.seen = {str(handle) for handle in initial}

    def take(self, messages):
        fresh = [(str(handle), props) for handle, props in messages.items() if str(handle) not in self.seen]
        self.seen.update(str(handle) for handle in messages)
        return fresh


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=int, choices=range(15, 301), default=180, metavar='15-300')
    args = parser.parse_args()
    client = None
    session = None
    try:
        system = dbus.SystemBus()
        objects = dbus.Interface(system.get_object('org.bluez', '/'), 'org.freedesktop.DBus.ObjectManager').GetManagedObjects(timeout=10)
        devices = devices_from(objects)
        for i, (_, props) in enumerate(devices, 1):
            print(f"{i}. {props.get('Alias', 'Paired device')}")
        if not devices:
            raise ValueError('No paired devices found.')
        choice = int(input('Type the LIST NUMBER for your iPhone (0 cancels): '))
        if choice == 0:
            return 0
        if not 1 <= choice <= len(devices):
            raise ValueError('Invalid list number.')
        props = devices[choice - 1][1]
        bus = dbus.SessionBus()
        client = dbus.Interface(bus.get_object(OBEX, '/org/bluez/obex'), OBEX+'.Client1')
        session = client.CreateSession(str(props['Address']), dbus.Dictionary({'Target': 'map'}, signature='sv'), timeout=30)
        access = dbus.Interface(bus.get_object(OBEX, session), MESSAGE_ACCESS)
        for folder in ('telecom', 'msg'):
            access.SetFolder(folder, timeout=15)
        filters = dbus.Dictionary({'MaxCount': dbus.UInt16(50), 'SubjectLength': dbus.Byte(255),
                                  'Fields': dbus.Array(['subject', 'timestamp', 'sender', 'sender-address', 'type'], signature='s')}, signature='sv')
        baseline = access.ListMessages('inbox', filters, timeout=20)
        tracker = FreshMessages(baseline)
        print('\nReady. Ask someone to send you a NEW text now.', flush=True)
        print('Existing messages are ignored. New texts display only in this terminal, with no disk history.', flush=True)
        print(f'Waiting up to {args.seconds} seconds; Ctrl+C stops. Do not paste private text into Codex.', flush=True)
        deadline = time.monotonic()+args.seconds
        while time.monotonic() < deadline:
            time.sleep(3)
            messages = access.ListMessages('inbox', filters, timeout=20)
            for _, message in tracker.take(messages):
                subject = str(message.get('Subject', ''))
                print('\nNEW INBOX MESSAGE', flush=True)
                print('From:', message.get('Sender', '') or message.get('SenderAddress', '(not provided)'), flush=True)
                print('Text preview:', subject or '(not supplied by phone)', flush=True)
                print('Fresh inbox entry received. Preview may be truncated; iMessage versus SMS is not identified by MAP.', flush=True)
                return 0
        print('No new inbox entry observed during this window; reception remains unverified.')
        return 1
    except dbus.DBusException as error:
        detail, hint = dbus_error_help(error.get_dbus_name(), error.get_dbus_message())
        print('Receive test failed:', detail, '\n'+hint)
        return 2
    except (ValueError, EOFError) as error:
        print(str(error))
        return 2
    except KeyboardInterrupt:
        print('\nReceive test stopped.')
        return 130
    finally:
        if session is not None:
            try:
                client.RemoveSession(session, timeout=10)
            except dbus.DBusException:
                print('Session cleanup could not be confirmed.')

if __name__ == '__main__':
    sys.exit(main())
