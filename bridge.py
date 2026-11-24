"""Serialized Bluetooth worker for the desktop client; no unattended sends."""
import os
from collections import deque
from pathlib import Path
import queue
import tempfile
import threading
import time
import dbus
from phonebridge import OBEX, MESSAGE_ACCESS, devices_from
from send_test import TransferEvents, make_bmessage, push_options, wait_transfer
from model import from_map
from history import MAX_MESSAGE_BYTES, parse_bmessage

class Bridge:
    def __init__(self, emit):
        self.emit = emit
        self.commands = queue.Queue()
        self.session = self.client = self.bus = self.access = self.match = None
        self.events = None
        self.seen = set()
        self.phone_address = None
        self.message_paths = {}
        self.loaded_bodies = set()
        self.pending_bodies = deque()
        self.thread = threading.Thread(target=self.run, name='phonebridge-bluetooth', daemon=True)
        self.thread.start()

    def command(self, action, value=None):
        self.commands.put((action, value))

    def close(self):
        if self.match:
            self.match.remove()
            self.match = None
        if self.session is not None:
            try:
                self.client.RemoveSession(self.session, timeout=5)
            except dbus.DBusException:
                pass
        self.session = self.access = self.events = None
        self.pending_bodies.clear()
        self.message_paths.clear()
        self.loaded_bodies.clear()

    def discover(self):
        system = dbus.SystemBus(private=True)
        try:
            objects = dbus.Interface(system.get_object('org.bluez', '/'), 'org.freedesktop.DBus.ObjectManager').GetManagedObjects(timeout=10)
            phones = [{'name': str(p.get('Alias', 'Paired phone')), 'address': str(p['Address'])}
                      for _, p in devices_from(objects)
                      if any(str(u).lower().startswith('00001132-') for u in p.get('UUIDs', []))]
            self.emit('devices', phones)
        finally:
            system.close()

    def connect(self, phone):
        self.close()
        if self.phone_address is not None and self.phone_address != phone['address']:
            self.emit('reset', None)
        self.phone_address = phone['address']
        self.emit('connecting', phone['name'])
        if self.bus is None:
            self.bus = dbus.SessionBus(private=True)
        self.client = dbus.Interface(self.bus.get_object(OBEX, '/org/bluez/obex'), OBEX+'.Client1')
        self.session = self.client.CreateSession(phone['address'], dbus.Dictionary({'Target': 'map'}, signature='sv'), timeout=30)
        self.access = dbus.Interface(self.bus.get_object(OBEX, self.session), MESSAGE_ACCESS)
        for folder in ('telecom', 'msg'):
            self.access.SetFolder(folder, timeout=15)
        self.events = TransferEvents(self.session)
        self.match = self.bus.add_signal_receiver(self.events.changed,
            signal_name='PropertiesChanged', dbus_interface='org.freedesktop.DBus.Properties',
            bus_name=OBEX, arg0=OBEX+'.Transfer1', path_keyword='path')
        self.seen = set()
        self.poll(initial=True)
        self.emit('connected', phone['name'])

    def poll(self, initial=False):
        filters = dbus.Dictionary({'MaxCount': dbus.UInt16(100), 'SubjectLength': dbus.Byte(255),
            'Fields': dbus.Array(['subject', 'timestamp', 'sender', 'sender-address', 'type'], signature='s')}, signature='sv')
        listing = self.access.ListMessages('inbox', filters, timeout=15)
        messages = [from_map(handle, props) for handle, props in listing.items()
                    if str(handle) not in self.seen]
        self.message_paths.update({str(handle).rsplit('/', 1)[-1]: str(handle) for handle in listing})
        self.seen.update(str(h) for h in listing)
        messages.sort(key=lambda m: (m.when, m.key))
        if messages or initial:
            self.emit('messages', {'initial': initial, 'items': messages})

    def load_body(self, key):
        path = self.message_paths.get(key)
        if not path or not self.session:
            self.emit('body', {'key': key, 'state': 'unavailable', 'text': None})
            return
        try:
            message = dbus.Interface(self.bus.get_object(OBEX, path), OBEX+'.Message1')
            with tempfile.TemporaryDirectory(prefix='phonebridge-read-') as directory:
                file = Path(directory)/'message.bmsg'
                transfer, initial = message.Get(str(file), dbus.Boolean(False), timeout=15)
                if int(initial.get('Size', 0)) > MAX_MESSAGE_BYTES:
                    try:
                        dbus.Interface(self.bus.get_object(OBEX, transfer), OBEX+'.Transfer1').Cancel(timeout=5)
                    finally:
                        raise ValueError('Message too large.')
                result = wait_transfer(self.bus, transfer, initial, self.events)
                if result is False:
                    raise ValueError('Download failed.')
                # A complete, parseable local bMessage can establish a read even
                # when the completed transfer object vanished before polling.
                for attempt in range(10):
                    if file.exists():
                        if file.stat().st_size > MAX_MESSAGE_BYTES:
                            raise ValueError('Message too large.')
                        os.chmod(file, 0o600)
                        data = file.read_bytes()
                        try:
                            text = parse_bmessage(data)
                            break
                        except ValueError:
                            if attempt == 9:
                                raise
                    time.sleep(.1)
                else:
                    raise ValueError('No complete downloaded message.')
            self.loaded_bodies.add(key)
            self.emit('body', {'key': key, 'state': 'full', 'text': text})
        except (dbus.DBusException, OSError, ValueError, LookupError, KeyError):
            # Keep the visible preview and mark the failed load explicitly.
            self.emit('body', {'key': key, 'state': 'unavailable', 'text': None})

    def send(self, request):
        attempted = False
        try:
            if not self.access:
                raise ValueError('Not connected. Nothing was submitted.')
            payload = make_bmessage(request['address'], request['text'])
            with tempfile.TemporaryDirectory(prefix='phonebridge-send-') as directory:
                file = Path(directory)/'outgoing.bmsg'
                fd = os.open(file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(payload)
                attempted = True
                path, initial = self.access.PushMessage(str(file), 'outbox', dbus.Dictionary(push_options(), signature='sv'), timeout=30)
                # GTK's main loop delivers status signals to TransferEvents while
                # this worker waits. Never iterate GTK from this thread.
                result = wait_transfer(self.bus, path, initial, self.events)
            state = 'accepted' if result is True else 'uncertain'
            self.emit('sent', {'id': request['id'], 'state': state,
                'detail': 'Accepted by iPhone; delivery not confirmed.' if state == 'accepted' else 'Receipt not confirmed. Check Messages on iPhone before sending again.'})
        except (dbus.DBusException, OSError, ValueError):
            if attempted:
                self.emit('sent', {'id': request['id'], 'state': 'uncertain',
                    'detail': 'Outcome uncertain. Check Messages on iPhone before sending again.'})
            else:
                # Nothing reached the phone: keep the draft and let the user try again.
                self.emit('sent', {'id': request['id'], 'state': 'not_sent',
                    'detail': 'Not sent: submission did not start, so the text never left this computer. Check the connection and recipient, then try again.'})

    def run(self):
        next_poll = time.monotonic()+4
        try:
            while True:
                try:
                    action, value = self.commands.get(timeout=.3)
                except queue.Empty:
                    action, value = None, None
                try:
                    if action == 'stop':
                        return
                    if action == 'discover':
                        self.discover()
                    elif action == 'connect':
                        self.connect(value)
                        next_poll = time.monotonic()+4
                    elif action == 'disconnect':
                        self.close()
                        self.emit('disconnected', 'Disconnected')
                    elif action == 'send':
                        self.send(value)
                    elif action == 'bodies':
                        self.pending_bodies = deque(k for k in dict.fromkeys(value) if k not in self.loaded_bodies)
                    elif action is None and self.access and self.pending_bodies:
                        self.load_body(self.pending_bodies.popleft())
                    if self.access and time.monotonic() >= next_poll:
                        self.poll()
                        next_poll = time.monotonic()+4
                except (dbus.DBusException, OSError, ValueError) as error:
                    self.close()
                    name = error.get_dbus_name() if isinstance(error, dbus.DBusException) else type(error).__name__
                    self.emit('error', name)
        finally:
            try:
                self.close()
                if self.bus is not None:
                    self.bus.close()
            finally:
                self.emit('stopped', None)
