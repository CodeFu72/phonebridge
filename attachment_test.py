#!/usr/bin/env python3
"""Inspect a fresh Bluetooth message for image bytes; never send or retain content."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from email import policy
from email.parser import BytesParser

MAX_BYTES = 12 * 1024 * 1024


def image_kind(data):
    if data.startswith(b'\xff\xd8\xff'):
        return 'jpeg'
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'png'
    if data.startswith((b'GIF87a', b'GIF89a')):
        return 'gif'
    if data.startswith(b'RIFF') and data[8:12] == b'WEBP':
        return 'webp'
    if len(data) >= 12 and data[4:8] == b'ftyp' and data[8:12] in (b'heic', b'heix', b'hevc', b'hevx', b'mif1', b'avif'):
        return 'heif/avif'
    return None


def inspect_attachment(data):
    if len(data) > MAX_BYTES:
        raise ValueError('Message exceeds the 12 MiB test limit.')
    if not data.rstrip(b'\r\n').endswith(b'END:BMSG'):
        raise ValueError('Downloaded message is incomplete; image access is unverified.')
    token = b'BEGIN:MSG\r\n'
    start, end = data.find(token), data.rfind(b'\r\nEND:MSG')
    if start < 0 or end < start + len(token):
        raise ValueError('No complete message envelope; image access is unverified.')
    content = data[start + len(token):end]
    mime = BytesParser(policy=policy.default).parsebytes(content)
    parts = list(mime.walk())
    images = []
    for part in parts:
        if part.is_multipart():
            continue
        payload = part.get_payload(decode=True) or b''
        kind = image_kind(payload)
        if kind:
            images.append({'format': kind, 'bytes': len(payload)})
    return {'download_bytes': len(data), 'mime_parts': len(parts),
            'image_parts_declared': sum(p.get_content_maintype() == 'image' for p in parts),
            'image_payloads_detected': images,
            'result': 'image bytes detected; display not yet tested' if images else
                      'no recognized image bytes found; this does not establish an iPhone limitation'}


def main():
    import dbus
    from dbus.mainloop.glib import DBusGMainLoop
    from phonebridge import OBEX, MESSAGE_ACCESS, devices_from, dbus_error_help
    from receive_test import FreshMessages
    from send_test import TransferEvents, wait_transfer, drain_events
    DBusGMainLoop(set_as_default=True)
    session = client = match = None
    stage = 'finding paired phones'
    try:
        print('Disconnect PhoneBridge before running this test. Keep your iPhone nearby and unlocked.')
        print('No sending, deletion, saved images or message-content output. Temporary downloads are removed on ordinary exit.')
        system = dbus.SystemBus()
        objects = dbus.Interface(system.get_object('org.bluez', '/'), 'org.freedesktop.DBus.ObjectManager').GetManagedObjects(timeout=10)
        phones = [(p, str(p.get('Alias', 'Phone'))) for _, p in devices_from(objects)
                  if any(str(u).lower().startswith('00001132-') for u in p.get('UUIDs', []))]
        for i, (_, name) in enumerate(phones, 1):
            print(f'{i}. {name}')
        if not phones:
            raise ValueError('No paired messaging phone found.')
        choice = int(input('Phone LIST NUMBER (0 cancels): '))
        if choice == 0:
            return 0
        if not 1 <= choice <= len(phones):
            raise ValueError('Invalid list number.')
        bus = dbus.SessionBus()
        client = dbus.Interface(bus.get_object(OBEX, '/org/bluez/obex'), OBEX+'.Client1')
        stage = 'opening Bluetooth messaging session'
        print('Opening Bluetooth messaging session…', flush=True)
        session = client.CreateSession(str(phones[choice-1][0]['Address']), dbus.Dictionary({'Target': 'map'}, signature='sv'), timeout=30)
        access = dbus.Interface(bus.get_object(OBEX, session), MESSAGE_ACCESS)
        stage = 'opening inbox folders'
        for folder in ('telecom', 'msg'):
            access.SetFolder(folder, timeout=15)
        filters = dbus.Dictionary({'MaxCount': dbus.UInt16(100), 'SubjectLength': dbus.Byte(0)}, signature='sv')
        stage = 'reading initial inbox listing'
        tracker = FreshMessages(access.ListMessages('inbox', filters, timeout=20))
        print('\nReady: have someone send ONE NEW harmless photo now. Waiting up to 180 seconds.', flush=True)
        deadline = time.monotonic() + 180
        fresh = []
        stage = 'waiting for a fresh inbox entry'
        while time.monotonic() < deadline:
            time.sleep(3)
            fresh = tracker.take(access.ListMessages('inbox', filters, timeout=20))
            if fresh:
                break
        if not fresh:
            print('No new message observed. Image access remains unverified.')
            return 1
        print(f'Observed {len(fresh)} new message(s). Only the first will be checked.')
        if input('Was that your harmless photo? Type CHECK to download it temporarily: ') != 'CHECK':
            print('Canceled without downloading.')
            return 0
        events = TransferEvents(session)
        match = bus.add_signal_receiver(events.changed, signal_name='PropertiesChanged',
                    dbus_interface='org.freedesktop.DBus.Properties', bus_name=OBEX,
                    arg0=OBEX+'.Transfer1', path_keyword='path')
        with tempfile.TemporaryDirectory(prefix='phonebridge-image-check-') as directory:
            file = Path(directory)/'message.bmsg'
            message = dbus.Interface(bus.get_object(OBEX, fresh[0][0]), OBEX+'.Message1')
            stage = 'downloading with attachments requested'
            transfer, initial = message.Get(str(file), dbus.Boolean(True), timeout=20)
            def bounded_pump():
                drain_events()
                if int(initial.get('Size', 0)) > MAX_BYTES or (file.exists() and file.stat().st_size > MAX_BYTES):
                    try:
                        dbus.Interface(bus.get_object(OBEX, transfer), OBEX+'.Transfer1').Cancel(timeout=5)
                    finally:
                        raise ValueError('Stopped: download exceeds the 12 MiB test limit.')
            try:
                bounded_pump()
                result = wait_transfer(bus, transfer, initial, events, bounded_pump)
                if result is False:
                    raise ValueError('Image download failed. Access remains unverified.')
                if not file.exists():
                    raise ValueError('No downloaded file found.')
                os.chmod(file, 0o600)
                bounded_pump()
                print('\nSafe summary (you can paste this into Codex):')
                summary = inspect_attachment(file.read_bytes())
                summary['transfer_receipt_confirmed'] = result is True
                print(json.dumps(summary, indent=2))
            finally:
                # Cancel queued/active work before deleting its temporary target.
                try:
                    dbus.Interface(bus.get_object(OBEX, transfer), OBEX+'.Transfer1').Cancel(timeout=5)
                except dbus.DBusException:
                    pass
        return 0
    except KeyboardInterrupt:
        print('\nAttachment test stopped.')
        return 130
    except dbus.DBusException as error:
        print('Failed while:', stage)
        print('Bluetooth attachment test failed:', error.get_dbus_name())
        detail, hint = dbus_error_help(error.get_dbus_name(), error.get_dbus_message())
        if stage == 'opening Bluetooth messaging session':
            print('Detail:', detail)
            print('Fully quit PhoneBridge through Settings or its tray menu before retrying. Closing its window may only hide it.')
        print(hint)
        print('No image support conclusion can be drawn from this error.')
        return 2
    except (OSError, ValueError, EOFError):
        print('Test canceled or download incomplete/oversized. Image access remains unverified.')
        return 2
    finally:
        if match:
            match.remove()
        if session is not None:
            try:
                client.RemoveSession(session, timeout=10)
            except dbus.DBusException:
                print('Session cleanup could not be confirmed.')


if __name__ == '__main__':
    sys.exit(main())
