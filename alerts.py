"""Generic desktop alerts and one quiet bundled ding, controlled by the user."""
from pathlib import Path
import shutil
import subprocess
import time
from gi.repository import Gio, GLib


def alert_policy(initial, fresh_count, enabled, sound):
    notify = bool(not initial and fresh_count > 0 and enabled)
    return notify, bool(notify and sound)


class Alerts:
    def __init__(self, notice=lambda text: None):
        self.notice = notice
        self.process = None
        self.last_sound = float('-inf')

    def incoming(self, initial, fresh_count, enabled, sound):
        show, ring = alert_policy(initial, fresh_count, enabled, sound)
        if show:
            self.notify()
        if ring:
            self.play_sound()

    def notify(self):
        # Suppress the notification daemon's own sound so Sound OFF really
        # stays silent and Sound ON does not produce two dings.
        def connected(source, result, _):
            try:
                connection = Gio.bus_get_finish(result)
                hints = {'suppress-sound': GLib.Variant('b', True),
                         'desktop-entry': GLib.Variant('s', 'io.phonebridge.Desktop')}
                parameters = GLib.Variant('(susssasa{sv}i)', ('PhoneBridge', 0, 'phonebridge',
                    'New text on your iPhone', 'Open PhoneBridge to read it.', [], hints, 5000))
                def finished(conn, response, _):
                    try:
                        conn.call_finish(response)
                    except GLib.Error:
                        self.notice('Desktop alert could not be shown. Check your desktop notification settings.')
                connection.call('org.freedesktop.Notifications', '/org/freedesktop/Notifications',
                    'org.freedesktop.Notifications', 'Notify', parameters, None,
                    Gio.DBusCallFlags.NONE, 5000, None, finished, None)
            except GLib.Error:
                self.notice('Desktop notifications are unavailable in this session.')
        Gio.bus_get(Gio.BusType.SESSION, None, connected, None)

    def play_sound(self):
        if time.monotonic()-self.last_sound < 1.5:
            return False
        if self.process is not None and self.process.poll() is None:
            return False
        file = str(Path(__file__).resolve().parent/'assets/ding.wav')
        player = shutil.which('pw-play') or shutil.which('paplay')
        command = [player, file] if player else None
        if command is None and (player := shutil.which('canberra-gtk-play')):
            command = [player, '--file', file]
        if command is None:
            self.notice('Sound needs pw-play, paplay, or canberra-gtk-play. Visual notifications still work.')
            return False
        try:
            self.process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.last_sound = time.monotonic()
            process = self.process
            def completed():
                result = process.poll()
                if result is None:
                    return True
                if result != 0:
                    self.notice('The notification sound could not play. Check your audio output and volume.')
                return False
            GLib.timeout_add(250, completed)
            return True
        except OSError:
            self.notice('The notification sound could not start. Visual notifications still work.')
            return False
