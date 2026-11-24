"""Local state and message presentation. Message bodies are never persisted."""
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import os
import re
from pathlib import Path
import tempfile
from send_test import MAX_TEXT_BYTES, recipient_field

@dataclass
class Message:
    key: str
    address: str
    name: str
    text: str
    when: str
    outgoing: bool = False
    status: str = ''
    body_state: str = 'preview'


def from_map(handle, props):
    return Message(str(handle).rsplit('/', 1)[-1], str(props.get('SenderAddress', '')),
                   str(props.get('Sender', '')) or str(props.get('SenderAddress', 'Unknown sender')),
                   str(props.get('Subject', '')) or '(No text preview supplied)',
                   str(props.get('Timestamp', '')))


def readable_time(value):
    try:
        return datetime.strptime(value.rstrip('Z'), '%Y%m%dT%H%M%S').strftime('%b %d · %I:%M %p')
    except ValueError:
        return value or 'Time unavailable'


class Favorites:
    def __init__(self, path=None):
        self.path = path or Path(os.environ.get('XDG_DATA_HOME', str(Path.home()/'.local/share')))/'phonebridge/favorites.json'
        self.items = {}
        if self.path.exists():
            data = json.loads(self.path.read_text())
            if not isinstance(data, dict):
                raise ValueError('Favorites file is invalid.')
            for address, name in data.items():
                recipient_field(address)
                if not isinstance(name, str) or len(name) > 200:
                    raise ValueError('Favorite name is invalid.')
            self.items = data

    def toggle(self, address, name):
        recipient_field(address)
        updated = dict(self.items)
        if address in updated:
            del updated[address]
        else:
            updated[address] = (name.strip() or address)[:200]
        self.save(updated)

    def save(self, updated):
        write_private_json(self.path, updated)
        self.items = updated


def write_private_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    fd, filename = tempfile.mkstemp(prefix='.favorites-' if path.name == 'favorites.json' else '.settings-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(data, stream, ensure_ascii=False)
            stream.write('\n')
        os.replace(filename, path)
    finally:
        Path(filename).unlink(missing_ok=True)


def contact_key(address):
    # Match a phone's +country-number and country-number spellings without
    # guessing a missing country code or changing the actual send recipient.
    address = address.strip()
    try:
        kind = recipient_field(address)
    except ValueError:
        return address
    return address.lstrip('+') if kind == 'TEL' else address


class Aliases(Favorites):
    def __init__(self, path=None):
        data = Path(os.environ.get('XDG_DATA_HOME', str(Path.home()/'.local/share')))
        super().__init__(path or data/'phonebridge/aliases.json')
        self.items = {contact_key(address): name for address, name in self.items.items()}

    def set_name(self, address, name):
        recipient_field(address)
        name = name.strip()
        if len(name) > 200 or any(ord(char) < 32 for char in name):
            raise ValueError('Use a name up to 200 characters without control characters.')
        updated = dict(self.items)
        key = contact_key(address)
        if name:
            updated[key] = name
        else:
            updated.pop(key, None)
        self.save(updated)


class Preferences:
    DEFAULTS = {'notifications_enabled': False, 'sound_enabled': True, 'tray_enabled': True, 'compact_window': True, 'animated_sky': True, 'glass': True}

    def __init__(self, path=None):
        data = Path(os.environ.get('XDG_DATA_HOME', str(Path.home()/'.local/share')))
        self.path = path or data/'phonebridge/preferences.json'
        self.items = dict(self.DEFAULTS)
        if self.path.exists():
            saved = json.loads(self.path.read_text())
            if not isinstance(saved, dict) or any(key not in self.DEFAULTS or type(value) is not bool for key, value in saved.items()):
                raise ValueError('Notification preferences are invalid.')
            self.items.update(saved)

    def set(self, enabled, sound, tray=None, compact=None, animated=None, glass=None):
        updated = {**self.items, 'notifications_enabled': bool(enabled), 'sound_enabled': bool(sound)}
        if tray is not None:
            updated['tray_enabled'] = bool(tray)
        if compact is not None:
            updated['compact_window'] = bool(compact)
        if animated is not None:
            updated['animated_sky'] = bool(animated)
        if glass is not None:
            updated['glass'] = bool(glass)
        write_private_json(self.path, updated)
        self.items = updated



class SendGate:
    """Only one outstanding send; uncertain sends require acknowledgement."""
    def __init__(self):
        self.state = 'idle'

    def begin(self):
        if self.state != 'idle':
            raise ValueError('Resolve the previous send before composing another.')
        self.state = 'pending'

    def finish(self, result):
        if self.state != 'pending':
            raise ValueError('No send is pending.')
        self.state = 'idle' if result == 'accepted' else 'uncertain'

    def acknowledge(self):
        if self.state != 'uncertain':
            raise ValueError('There is no uncertain send to acknowledge.')
        self.state = 'idle'


class Unread:
    """Local unread state only; never modifies iPhone read flags."""
    def __init__(self):
        self.items = {}

    def incoming(self, messages, initial=False, viewed_peer=None):
        if initial:
            return
        for message in messages:
            key = contact_key(message.address)
            if not message.outgoing and key != viewed_peer:
                self.items.setdefault(key, set()).add(message.key)

    def read(self, address):
        self.items.pop(contact_key(address), None)

    def count(self, address):
        return len(self.items.get(contact_key(address), ()))

    @property
    def total(self):
        return sum(len(keys) for keys in self.items.values())


def hide_on_close(tray_enabled, tray_ready):
    return bool(tray_enabled and tray_ready)


def insert_emoji(text, emoji, position, selection=()):
    """Replace a character selection or insert at the caret within the byte budget."""
    if len(selection) == 3:
        selected, start, end = selection
        selection = (start, end) if selected else ()
    if selection:
        start, end = sorted(selection)
    else:
        start = end = len(text) if position < 0 else position
    start, end = max(0, min(start, len(text))), max(0, min(end, len(text)))
    updated = text[:start] + emoji + text[end:]
    if len(updated.encode('utf-8')) > MAX_TEXT_BYTES:
        raise ValueError(f'That emoji would exceed {MAX_TEXT_BYTES} UTF-8 bytes. Shorten your text first.')
    return updated, start + len(emoji)


def conversation_order(peers, messages):
    """Newest conversation first; saved contacts without texts follow by name."""
    latest = {}
    for message in messages:
        key = contact_key(message.address)
        latest[key] = max(latest.get(key, ''), message.when)
    return sorted(sorted(peers.items(), key=lambda item: item[1][1].casefold()),
                  key=lambda item: latest.get(item[0], ''), reverse=True)


class ClearedThreads:
    """Persist only hashes of dismissed message identities and contact keys."""
    def __init__(self, path=None, memory_only=False):
        self.path = path or Path(os.environ.get('XDG_DATA_HOME', str(Path.home()/'.local/share')))/'phonebridge/cleared.json'
        self.memory_only = memory_only
        data = {} if memory_only or not self.path.exists() else json.loads(self.path.read_text())
        if not isinstance(data, dict):
            raise ValueError('Invalid cleared-thread data.')
        for field in ('messages', 'peers'):
            values = data.get(field, [])
            if not isinstance(values, list) or any(not isinstance(v, str) or len(v) != 64 or any(c not in '0123456789abcdef' for c in v) for v in values):
                raise ValueError('Invalid cleared-thread data.')
        self.messages = set(data.get('messages', []))
        self.peers = set(data.get('peers', []))

    @staticmethod
    def digest(*parts):
        return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()

    def identity(self, message):
        return self.digest(contact_key(message.address), message.key, message.when)

    def visible(self, message):
        return self.identity(message) not in self.messages

    def cleared(self, address):
        return self.digest(contact_key(address)) in self.peers

    def clear(self, address, messages):
        key = contact_key(address)
        updated = self.messages | {self.identity(m) for m in messages if contact_key(m.address) == key}
        peers = self.peers | {self.digest(key)}
        if not self.memory_only:
            write_private_json(self.path, {'messages': sorted(updated), 'peers': sorted(peers)})
        self.messages, self.peers = updated, peers


def clean_compose_text(text, max_chars=MAX_TEXT_BYTES):
    """Line breaks are kept (as \\n); tabs become spaces; cap length."""
    flat = text.replace('\r\n', '\n').replace('\r', '\n').replace('\t', ' ')
    return flat[:max_chars]


# http(s) links and bare www. links; trailing punctuation stays outside the link.
_LINK = re.compile(r'(?i)\b(?:https?://|www\.)[^\s<>"]+')
_TRAILING = '.,;:!?\'")]}>'


def find_links(text):
    """Return (start, end, url) for each link; bare www. links get https://."""
    links = []
    for match in _LINK.finditer(text):
        start, end = match.span()
        while end > start and text[end-1] in _TRAILING:
            if text[end-1] == ')' and text[start:end].count('(') >= text[start:end].count(')'):
                break
            end -= 1
        raw = text[start:end]
        if '.' not in raw.split('//', 1)[-1]:
            continue
        links.append((start, end, raw if raw.lower().startswith('http') else 'https://' + raw))
    return links


def linkify_markup(text):
    """Pango markup for a message: escaped text with clickable http(s) links."""
    from html import escape
    parts, last = [], 0
    for start, end, url in find_links(text):
        parts.append(escape(text[last:start], quote=False))
        parts.append(f'<a href="{escape(url, quote=True)}">{escape(text[start:end], quote=False)}</a>')
        last = end
    parts.append(escape(text[last:], quote=False))
    return ''.join(parts)
