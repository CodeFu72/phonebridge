#!/usr/bin/env python3
"""Send one user-composed text after explicit terminal confirmation. No retries."""
import os
from pathlib import Path
import re
import sys
import tempfile
import time
import dbus
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib
from phonebridge import OBEX, MESSAGE_ACCESS, devices_from

# Longest text PhoneBridge sends, in UTF-8 bytes (an emoji counts as 4). Was 500 until 2026-11-19.
MAX_TEXT_BYTES = 2000


def push_options():
    # BlueZ parse_charset accepts 'utf8', not the bMessage label 'UTF-8'.
    return {'Charset': 'utf8', 'Transparent': False, 'Retry': False}


def recipient_field(address):
    if re.fullmatch(r'\+?[0-9]{7,15}', address):
        return 'TEL'
    if re.fullmatch(r'[A-Za-z0-9.!#$%&\x27*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}', address):
        return 'EMAIL'
    raise ValueError('Enter one phone number (digits and optional leading +) or an Apple-ID email address. No names or lists.')


def make_bmessage(address, text):
    field = recipient_field(address)
    if not text.strip() or len(text.encode('utf-8')) > MAX_TEXT_BYTES:
        raise ValueError(f'Use a nonempty message of at most {MAX_TEXT_BYTES} UTF-8 bytes.')
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    if any((ord(char) < 32 and char != '\n') or ord(char) == 127 for char in text):
        raise ValueError('Line breaks are fine, but other control characters are not.')
    lines_out = text.split('\n')
    if any(line.upper().startswith(('BEGIN:', 'END:')) for line in lines_out):
        raise ValueError('A line can\'t start with BEGIN: or END: (they would break the Bluetooth message).')
    # Line breaks travel as CRLF inside the bMessage body; LENGTH counts them.
    block = 'BEGIN:MSG\r\n'+'\r\n'.join(lines_out)+'\r\nEND:MSG\r\n'
    lines = ['BEGIN:BMSG', 'VERSION:1.4', 'STATUS:UNREAD', 'TYPE:SMS_GSM',
             'FOLDER:telecom/msg/outbox', 'BEGIN:VCARD', 'VERSION:2.1', 'N:', 'FN:', 'END:VCARD',
             'BEGIN:BENV', 'BEGIN:VCARD', 'VERSION:2.1', 'N:', 'FN:', f'{field}:{address}', 'END:VCARD',
             'BEGIN:BBODY', 'CHARSET:UTF-8', 'LENGTH:'+str(len(block.encode('utf-8')))]
    return ('\r\n'.join(lines)+'\r\n'+block+'END:BBODY\r\nEND:BENV\r\nEND:BMSG\r\n').encode('utf-8')


class TransferEvents:
    def __init__(self, session):
        self.session = str(session)
        self.statuses = {}

    def changed(self, interface, changed, invalidated, path=None):
        if (str(interface) == OBEX+'.Transfer1' and path is not None
                and str(path).startswith(self.session+'/') and 'Status' in changed):
            key = str(path)
            # Never overwrite an observed terminal receipt with an older state.
            if self.statuses.get(key) not in ('complete', 'error'):
                self.statuses[key] = str(changed['Status'])


def wait_transfer(bus, path, initial, events=None, pump=None):
    status = str(initial.get('Status', 'queued'))
    deadline = time.monotonic()+30
    missing_since = None
    while True:
        if pump:
            pump()
        if events:
            status = events.statuses.get(str(path), status)
        if status == 'complete':
            return True
        if status == 'error':
            return False
        if time.monotonic() >= deadline:
            return None
        time.sleep(.1)
        try:
            properties = dbus.Interface(bus.get_object(OBEX, path, introspect=False), 'org.freedesktop.DBus.Properties')
            status = str(properties.Get(OBEX+'.Transfer1', 'Status', timeout=5))
        except dbus.DBusException as error:
            if error.get_dbus_name() != 'org.freedesktop.DBus.Error.UnknownObject':
                raise
            # Completion may already be queued as a signal when the object goes
            # away. Drain for a short grace period; disappearance is not success.
            if missing_since is None:
                missing_since = time.monotonic()
            if time.monotonic()-missing_since >= 1:
                if pump:
                    pump()
                if events:
                    terminal = events.statuses.get(str(path))
                    if terminal in ('complete', 'error'):
                        return terminal == 'complete'
                return None


def drain_events():
    context = GLib.MainContext.default()
    while context.pending():
        context.iteration(False)


def main():
    session = client = None
    attempted = False
    stage = "device selection"
    signal_match = None
    DBusGMainLoop(set_as_default=True)
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
        address = input('Recipient PHONE NUMBER or Apple-ID email (not a contact name): ').strip()
        recipient_field(address)
        text = input('Short test text (one line): ')
        payload = make_bmessage(address, text)
        print('\nRecipient:', address, '\nMessage:', text)
        print('One recipient only. The iPhone chooses iMessage or SMS; SMS may use your carrier plan.')
        if input('Type SEND to send this exact text, or anything else to cancel: ') != 'SEND':
            print('Canceled. Nothing sent.')
            return 0
        bus = dbus.SessionBus()
        client = dbus.Interface(bus.get_object(OBEX, '/org/bluez/obex'), OBEX+'.Client1')
        stage = "opening messaging session"
        session = client.CreateSession(str(devices[choice-1][1]['Address']), dbus.Dictionary({'Target': 'map'}, signature='sv'), timeout=30)
        access = dbus.Interface(bus.get_object(OBEX, session), MESSAGE_ACCESS)
        stage = 'selecting outbox folder'
        for folder in ('telecom', 'msg'):
            access.SetFolder(folder, timeout=15)
        events = TransferEvents(session)
        signal_match = bus.add_signal_receiver(events.changed,
            signal_name='PropertiesChanged', dbus_interface='org.freedesktop.DBus.Properties',
            bus_name=OBEX, arg0=OBEX+'.Transfer1', path_keyword='path')
        # TemporaryDirectory uses owner-only access; the message file is 0600.
        with tempfile.TemporaryDirectory(prefix='phonebridge-send-') as directory:
            file = Path(directory)/'outgoing.bmsg'
            fd = os.open(file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(payload)
            stage = "submitting message"
            attempted = True
            transfer, initial = access.PushMessage(str(file), 'outbox', dbus.Dictionary(push_options(), signature='sv'), timeout=30)
            stage = "checking transfer receipt"
            result = wait_transfer(bus, transfer, initial, events, drain_events)
        if result is True:
            print('The iPhone accepted the message transfer. Check Messages on the iPhone and ask the recipient to confirm receipt.')
            print('Recipient delivery and iMessage versus SMS are not verified by this result.')
            return 0
        print('Transfer failed or its outcome is uncertain. Check the iPhone before attempting another send. No retry performed.')
        return 1
    except dbus.DBusException as error:
        # Omit raw send errors: a remote error might echo message/recipient data.
        print('Bluetooth operation failed during '+stage+':', error.get_dbus_name())
        if attempted:
            print('Send outcome is uncertain. Check Messages on the iPhone before trying again. No retry performed.')
        else:
            print('The message submission was not started.')
        return 2
    except (ValueError, EOFError) as error:
        print(str(error))
        return 2
    except KeyboardInterrupt:
        print('\nStopped. Check the iPhone before retrying if submission had started.' if attempted else '\nCanceled before submission.')
        return 130
    finally:
        if signal_match is not None:
            signal_match.remove()
        if session is not None:
            try:
                client.RemoveSession(session, timeout=10)
            except dbus.DBusException:
                print('Session cleanup could not be confirmed.')

if __name__ == '__main__':
    sys.exit(main())
