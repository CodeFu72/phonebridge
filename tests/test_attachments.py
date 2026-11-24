import base64
import unittest
from attachment_test import inspect_attachment, MAX_BYTES


def envelope(body):
    return b'BEGIN:BMSG\r\nBEGIN:MSG\r\n'+body+b'\r\nEND:MSG\r\nEND:BMSG\r\n'


class AttachmentTests(unittest.TestCase):
    def test_image_payload_detected_without_private_output(self):
        image = b'\x89PNG\r\n\x1a\n' + b'example'
        body = (b'MIME-Version: 1.0\r\nContent-Type: multipart/mixed; boundary=x\r\n\r\n'
                b'--x\r\nContent-Type: text/plain\r\n\r\nsecret text\r\n'
                b'--x\r\nContent-Type: image/png\r\nContent-Disposition: attachment; filename="secret.png"\r\n'
                b'Content-Transfer-Encoding: base64\r\n\r\n' + base64.b64encode(image) + b'\r\n--x--\r\n')
        summary = inspect_attachment(envelope(body))
        self.assertEqual(summary['image_payloads_detected'], [{'format': 'png', 'bytes': len(image)}])
        self.assertNotIn('secret', str(summary))

    def test_placeholder_is_not_image_support(self):
        summary = inspect_attachment(envelope(b'Content-Type: image/jpeg\r\n\r\nPhoto placeholder'))
        self.assertEqual(summary['image_parts_declared'], 1)
        self.assertEqual(summary['image_payloads_detected'], [])

    def test_plain_text(self):
        self.assertEqual(inspect_attachment(envelope(b'hello'))['image_payloads_detected'], [])

    def test_incomplete_rejected(self):
        with self.assertRaises(ValueError): inspect_attachment(envelope(b'hello')[:-12])

    def test_oversize_rejected(self):
        with self.assertRaises(ValueError): inspect_attachment(b'x'*(MAX_BYTES+1))
