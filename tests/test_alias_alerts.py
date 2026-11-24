from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from model import Aliases, Favorites, Preferences, contact_key
from alerts import Alerts, alert_policy

class AliasTests(unittest.TestCase):
    def test_alias_can_be_renamed_and_removed_without_touching_favorites(self):
        with tempfile.TemporaryDirectory() as directory:
            aliases = Aliases(Path(directory)/'aliases.json')
            favorites = Favorites(Path(directory)/'favorites.json')
            favorites.toggle('+15551234567', 'Original')
            aliases.set_name('+15551234567', 'Home')
            self.assertEqual(Aliases(aliases.path).items[contact_key('15551234567')], 'Home')
            aliases.set_name('15551234567', 'Family')
            self.assertEqual(len(aliases.items), 1)
            self.assertEqual(aliases.items[contact_key('+15551234567')], 'Family')
            aliases.set_name('+15551234567', '')
            self.assertEqual(Aliases(aliases.path).items, {})
            self.assertEqual(Favorites(favorites.path).items, {'+15551234567': 'Original'})
            self.assertEqual(aliases.path.stat().st_mode & 0o777, 0o600)

    def test_no_country_code_guessing_and_no_structural_recipient_alias(self):
        self.assertNotEqual(contact_key('+15551234567'), contact_key('5551234567'))
        with tempfile.TemporaryDirectory() as directory:
            aliases = Aliases(Path(directory)/'aliases.json')
            for address, name in [('Unknown Name', 'Alias'), ('+15551234567', 'x\nInjected')]:
                with self.assertRaises(ValueError):
                    aliases.set_name(address, name)
            self.assertFalse(aliases.path.exists())

class NotificationTests(unittest.TestCase):
    def test_switches_persist_privately_and_default_off(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'preferences.json'
            settings = Preferences(path)
            self.assertFalse(settings.items['notifications_enabled'])
            settings.set(True, False)
            self.assertEqual(Preferences(path).items, {**Preferences.DEFAULTS, 'notifications_enabled': True, 'sound_enabled': False})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            settings.set(False, True)
            self.assertEqual(alert_policy(False, 1, **{'enabled': settings.items['notifications_enabled'], 'sound': settings.items['sound_enabled']}), (False, False))

    def test_no_alert_for_initial_history_empty_poll_or_master_off(self):
        for initial, count, enabled, sound, expected in [
            (True, 100, True, True, (False, False)),
            (False, 0, True, True, (False, False)),
            (False, 1, False, True, (False, False)),
            (False, 1, True, False, (True, False)),
            (False, 3, True, True, (True, True))]:
            self.assertEqual(alert_policy(initial, count, enabled, sound), expected)

    def test_one_ding_per_incoming_batch_and_none_when_disabled(self):
        alerts = Alerts()
        alerts.notify = Mock(); alerts.play_sound = Mock()
        alerts.incoming(False, 5, True, True)
        alerts.notify.assert_called_once(); alerts.play_sound.assert_called_once()
        alerts.incoming(True, 20, True, True)
        alerts.incoming(False, 1, False, True)
        alerts.notify.assert_called_once(); alerts.play_sound.assert_called_once()

    def test_audio_playback_is_local_and_rate_limited(self):
        alerts = Alerts()
        process = Mock(); process.poll.return_value = None
        with patch('alerts.shutil.which', return_value='/usr/bin/pw-play'), patch('alerts.subprocess.Popen', return_value=process) as spawn, patch('alerts.GLib.timeout_add'), patch('alerts.time.monotonic', return_value=10):
            self.assertTrue(alerts.play_sound())
            self.assertFalse(alerts.play_sound())
        spawn.assert_called_once()
        self.assertEqual(spawn.call_args.args[0][0], '/usr/bin/pw-play')
        self.assertTrue(spawn.call_args.args[0][1].endswith('/assets/ding.wav'))

    def test_missing_sound_player_reports_problem_without_crashing(self):
        notice = Mock(); alerts = Alerts(notice)
        with patch('alerts.shutil.which', return_value=None):
            self.assertFalse(alerts.play_sound())
        notice.assert_called_once()
