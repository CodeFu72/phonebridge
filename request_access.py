#!/usr/bin/env python3
"""Temporarily solicit iPhone notification access; never read or send messages."""
import signal
import sys
import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib, GLibUnix
from phonebridge import ANCS, devices_from, dbus_error_help

PATH = '/org/phonebridge/access_advertisement'
AD = 'org.bluez.LEAdvertisement1'
MANAGER = 'org.bluez.LEAdvertisingManager1'

class Advertisement(dbus.service.Object):
    @dbus.service.method('org.freedesktop.DBus.Properties', in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != AD:
            raise dbus.exceptions.DBusException('Unknown interface', name='org.freedesktop.DBus.Error.InvalidArgs')
        return dbus.Dictionary({
            'Type': dbus.String('peripheral'),
            'SolicitUUIDs': dbus.Array([ANCS], signature='s'),
            'LocalName': dbus.String('PhoneBridge'),
            'Discoverable': dbus.Boolean(True),
            'Timeout': dbus.UInt16(90),
        }, signature='sv')

    @dbus.service.method(AD, in_signature='', out_signature='')
    def Release(self):
        GLib.idle_add(loop.quit)


def main(selected=None):
    global loop
    DBusGMainLoop(set_as_default=True)
    loop = GLib.MainLoop()
    manager = advert = None
    registered = False
    registration_failed = False
    input_watch = None
    sources = []
    try:
        bus = dbus.SystemBus()
        objects = dbus.Interface(bus.get_object('org.bluez', '/'), 'org.freedesktop.DBus.ObjectManager').GetManagedObjects(timeout=10)
        if selected is None:
            devices = devices_from(objects)
            if not devices:
                print('No paired device found. Pair the iPhone first.')
                return 2
            for number, (_, candidate) in enumerate(devices, 1):
                print(f"{number}. {candidate.get('Alias', 'Paired device')}")
            choice = int(input('Type the LIST NUMBER for your iPhone (0 cancels): '))
            if choice == 0:
                return 0
            if not 1 <= choice <= len(devices):
                raise ValueError('Invalid device selection.')
            _, props = devices[choice - 1]
        else:
            props = selected
        adapter = str(props['Adapter'])
        if MANAGER not in objects.get(adapter, {}):
            print('This adapter does not expose LE advertising. No settings changed.')
            return 2
        manager = dbus.Interface(bus.get_object('org.bluez', adapter), MANAGER)
        advert = Advertisement(bus, PATH)
        def ready():
            nonlocal registered, input_watch
            registered = True
            print('\nAccessory signal active for up to 90 seconds. No message content is accessed.', flush=True)
            adapter_props = objects.get(adapter, {}).get('org.bluez.Adapter1', {})
            computer_name = str(adapter_props.get('Alias', 'this computer'))
            print('On iPhone: Settings > Bluetooth > (i) beside '+computer_name+'.', flush=True)
            print('Leave and reopen that detail page; look for Show Message Notifications.', flush=True)
            print('If it appears, enable it. Accept a notification-sharing prompt if one appears.', flush=True)
            print('When enabled, press Enter here to continue, or let the signal expire.', flush=True)
            if sys.stdin.isatty():
                def continue_setup(*_):
                    sys.stdin.readline()
                    loop.quit()
                    return True
                input_watch = GLib.io_add_watch(sys.stdin, GLib.IO_IN | GLib.IO_HUP, continue_setup)
            print('Ctrl+C ends the signal. Pairing and adapter identity remain unchanged.', flush=True)
            sources.append(GLib.timeout_add_seconds(90, lambda: (loop.quit(), True)[1]))

        def failed(error):
            nonlocal registration_failed
            registration_failed = True
            detail, hint = dbus_error_help(error.get_dbus_name(), error.get_dbus_message())
            print('Advertisement registration failed:', detail, '\n'+hint, flush=True)
            loop.quit()

        # BlueZ calls GetAll on this exported object during registration; keep
        # the GLib loop running instead of blocking it with a synchronous call.
        manager.RegisterAdvertisement(PATH, dbus.Dictionary({}, signature='sv'),
                                      reply_handler=ready, error_handler=failed, timeout=15)
        sources.append(GLibUnix.signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, lambda: (loop.quit(), True)[1]))
        sources.append(GLibUnix.signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, lambda: (loop.quit(), True)[1]))
        loop.run()
        if registration_failed:
            return 2
        print('Temporary accessory signal ended.')
        return 0
    except dbus.DBusException as error:
        detail, hint = dbus_error_help(error.get_dbus_name(), error.get_dbus_message())
        print('Accessory setup failed:', error.get_dbus_name(), '\nDetail:', detail, '\n'+hint)
        return 2
    except (ValueError, EOFError) as error:
        print(str(error))
        return 2
    finally:
        for source in sources:
            GLib.source_remove(source)
        if input_watch is not None:
            GLib.source_remove(input_watch)
        if registered:
            try:
                manager.UnregisterAdvertisement(PATH, timeout=10)
            except dbus.DBusException:
                pass  # BlueZ may already have released the bounded advertisement.
        if advert:
            advert.remove_from_connection()

if __name__ == '__main__':
    sys.exit(main())
