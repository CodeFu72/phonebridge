from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import dbus
from history import MAX_MESSAGE_BYTES, near_bottom, parse_bmessage
from bridge import Bridge
from app import Window


def envelope(text):
    return ('BEGIN:BMSG\r\nVERSION:1.4\r\nBEGIN:BBODY\r\nBEGIN:MSG\r\n'+text+'\r\nEND:MSG\r\nEND:BBODY\r\nEND:BMSG\r\n').encode('utf-8')


class FullTextTests(unittest.TestCase):
    def test_long_unicode_multiline_text_is_not_cut_to_preview(self):
        text = 'Long text 🙂 '+('a'*800)+'\r\nAnother paragraph\r\nA long URL: '+('x'*300)
        self.assertEqual(parse_bmessage(envelope(text)), text.replace('\r\n','\n'))

    def test_incomplete_download_is_not_mislabeled_as_full(self):
        for data in (b'BEGIN:BMSG\r\nBEGIN:MSG\r\npartial', b'END:BMSG', b'x'*(MAX_MESSAGE_BYTES+1)):
            with self.assertRaises(ValueError):
                parse_bmessage(data)

    def test_structural_looking_text_is_unescaped_without_eating_real_text(self):
        text = '/BEGIN:example\r\n/END:MSG\r\nlast line'
        self.assertEqual(parse_bmessage(envelope(text)), 'BEGIN:example\nEND:MSG\nlast line')

    def test_plain_mime_body_decodes_quoted_printable(self):
        text = 'Content-Type: text/plain; charset=utf-8\r\nContent-Transfer-Encoding: quoted-printable\r\n\r\nHello=20world'
        self.assertEqual(parse_bmessage(envelope(text)), 'Hello world')

    def test_worker_fetches_complete_body_without_attachments_or_persistence(self):
        worker = Bridge.__new__(Bridge)
        worker.message_paths = {'message1': '/session/message1'}
        worker.loaded_bodies = set(); worker.session='/session'; worker.bus=Mock(); worker.events=Mock(); worker.emit=Mock()
        interface=Mock(); paths=[]
        text='Full incoming text '+('z'*900)
        def get(filename, attachment, **kwargs):
            self.assertFalse(attachment)
            path=Path(filename);paths.append(path)
            self.assertEqual(path.parent.stat().st_mode&0o777,0o700)
            path.write_bytes(envelope(text))
            return '/session/transfer1', {'Status':'complete'}
        interface.Get.side_effect=get
        with patch('bridge.dbus.Interface',return_value=interface),patch('bridge.wait_transfer',return_value=True):
            worker.load_body('message1')
        worker.emit.assert_called_once_with('body',{'key':'message1','state':'full','text':text})
        self.assertFalse(paths[0].exists())
        interface.Set.assert_not_called()

    def test_empty_poll_does_not_emit_a_chat_redraw(self):
        worker=Bridge.__new__(Bridge)
        worker.access=Mock();worker.access.ListMessages.return_value={}
        worker.seen=set();worker.message_paths={};worker.emit=Mock()
        worker.poll()
        worker.emit.assert_not_called()


class ScrollTests(unittest.TestCase):
    def test_follow_only_when_already_near_bottom(self):
        self.assertTrue(near_bottom(600,1000,400))
        self.assertTrue(near_bottom(575,1000,400))
        self.assertFalse(near_bottom(120,1000,400))
        self.assertTrue(near_bottom(0,200,400))

    def test_pending_scroll_callback_cannot_pull_reader_down(self):
        window=SimpleNamespace(follow_history_latest=False,thread_scroll=Mock(),latest_button=Mock())
        Window.scroll_bottom(window)
        window.thread_scroll.get_vadjustment.assert_not_called()

    def test_empty_gui_poll_preserves_rows_and_position(self):
        from model import Unread
        window=SimpleNamespace(messages=[],unread=Unread(),get_visible=Mock(return_value=False),get_application=Mock(),render_sidebar=Mock(),render_thread=Mock(),request_bodies=Mock(),
            alerts=Mock(),notifications=Mock(),sound=Mock(),update_controls=Mock())
        Window.event(window,'messages',{'initial':False,'items':[]})
        window.render_thread.assert_not_called()
        window.render_sidebar.assert_not_called()
