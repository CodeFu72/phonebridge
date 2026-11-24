import unittest
from receive_test import FreshMessages

class FreshMessageTests(unittest.TestCase):
    def test_old_messages_and_repeat_polls_are_not_displayed(self):
        tracker = FreshMessages({'old': {'Subject': 'old private text'}})
        self.assertEqual(tracker.take({'old': {'Subject': 'changed preview'}}), [])
        self.assertEqual(tracker.take({'old': {}, 'new': {'Subject': 'fresh'}}), [('new', {'Subject': 'fresh'})])
        self.assertEqual(tracker.take({'new': {'Subject': 'fresh'}}), [])

    def test_disappearing_old_message_stays_ignored(self):
        tracker = FreshMessages({'old': {}})
        tracker.take({})
        self.assertEqual(tracker.take({'old': {}}), [])
