"""Full text extraction and scroll-follow decisions; no persistent history."""
from email.parser import BytesParser
from email import policy

MAX_MESSAGE_BYTES = 2 * 1024 * 1024


def near_bottom(value, upper, page_size, tolerance=40):
    return max(0, upper-page_size)-value <= tolerance


def _content(part):
    """Decoded text; an unknown or broken charset label falls back to UTF-8 with replacements."""
    try:
        return part.get_content()
    except (LookupError, KeyError):
        return (part.get_payload(decode=True) or b'').decode('utf-8', errors='replace')


def parse_bmessage(data):
    if len(data) > MAX_MESSAGE_BYTES:
        raise ValueError('Message exceeds the text-download limit.')
    if not data.rstrip(b'\r\n').endswith(b'END:BMSG'):
        raise ValueError('Message download is incomplete.')
    start_token = b'BEGIN:MSG\r\n'
    start = data.find(start_token)
    end = data.rfind(b'\r\nEND:MSG')
    if start < 0 or end < start + len(start_token):
        raise ValueError('No complete text body found.')
    content = data[start+len(start_token):end]
    # MAP escapes structural-looking text lines with a leading slash.
    content = b'\r\n'.join(line[1:] if line.startswith((b'/BEGIN:', b'/END:')) else line for line in content.split(b'\r\n'))
    if content.lower().startswith((b'content-type:', b'mime-version:')):
        message = BytesParser(policy=policy.default).parsebytes(content)
        if message.is_multipart():
            part = message.get_body(preferencelist=('plain',))
            if part is None:
                raise ValueError('No plain text in this message; view it on iPhone.')
            text = _content(part)
        elif message.get_content_type() == 'text/plain':
            text = _content(message)
        else:
            raise ValueError('This message is not plain text; view it on iPhone.')
        return str(text).replace('\r\n', '\n')
    return content.decode('utf-8', errors='replace').replace('\r\n', '\n')
