"""Colors from the running Omarchy theme, so PhoneBridge's glass look follows it.

Omarchy writes the current theme's palette to ~/.local/state/omarchy/current/theme/colors.toml
and bumps theme.generation every time the theme changes. We read the palette, turn it into
GTK @define-color lines, and watch theme.generation to restyle live.
"""
import re
import tomllib
from pathlib import Path

from gi.repository import Gio, GLib

STATE = Path.home()/'.local/state/omarchy/current'
HEX = re.compile(r'#[0-9a-fA-F]{6}')

# Vesper's night sky, used when no Omarchy theme can be read.
FALLBACK = {
    'mode': 'dark',
    'background': '#1d2733',
    'lighter_background': '#2a3747',
    'foreground': '#e8edf3',
    'accent': '#a9c2e9',
    'red': '#f0b3a6',
    'yellow': '#e8cf9a',
    'green': '#a6da95',
}


def colors(path=None):
    path = path or STATE/'theme/colors.toml'
    try:
        data = tomllib.loads(Path(path).read_text())
    except (OSError, ValueError):
        data = {}
    out = dict(FALLBACK)
    for key, value in data.items():
        if isinstance(value, str) and HEX.fullmatch(value):
            out[key] = value
    if data.get('mode') in ('light', 'dark'):
        out['mode'] = data['mode']
    return out


def defines(c):
    """GTK named colors the glass stylesheet uses."""
    pairs = {
        't_bg': c['background'],
        't_raised': c.get('lighter_background', c['background']),
        't_fg': c['foreground'],
        't_accent': c['accent'],
        't_danger': c['red'],
        't_warm': c['yellow'],
        't_ok': c['green'],
    }
    lines = [f'@define-color {name} {value};' for name, value in pairs.items()]
    # Light themes get a lighter pane of glass and darker lines.
    lines.append('@define-color t_shadow ' + ('rgba(0,0,0,0.10)' if c['mode'] == 'light' else 'rgba(0,0,0,0.35)') + ';')
    return '\n'.join(lines) + '\n'


def stylesheet(css_path, colors_path=None):
    return defines(colors(colors_path)) + Path(css_path).read_text()


class Watcher:
    """Calls back (once, shortly after) whenever Omarchy switches themes."""

    def __init__(self, callback):
        self.callback = callback
        self.pending = 0
        self.monitors = []
        for name in ('theme.generation', 'theme.name'):
            monitor = Gio.File.new_for_path(str(STATE/name)).monitor_file(Gio.FileMonitorFlags.NONE, None)
            monitor.connect('changed', self.changed)
            self.monitors.append(monitor)

    def changed(self, *_):
        if self.pending:
            GLib.source_remove(self.pending)
        self.pending = GLib.timeout_add(400, self.fire)

    def fire(self):
        self.pending = 0
        self.callback()
        return False
