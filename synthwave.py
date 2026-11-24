"""PhoneBridge's synthwave look, borrowed from Rinse: night sky, striped sun,
a slow neon grid, and a chrome logo. Drawn natively with Cairo."""
import math
from pathlib import Path

import cairo
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('PangoCairo', '1.0')
gi.require_version('Graphene', '1.0')
from gi.repository import Gtk, Gdk, GLib, Graphene, Pango, PangoCairo

FONTS = Path(__file__).resolve().parent / 'assets' / 'fonts'
PINK = (1.0, 0.18, 0.53)
TEAL = (0.18, 0.89, 0.90)


def register_fonts():
    """Make the bundled Monoton and Orbitron fonts available to GTK (no install needed)."""
    font_map = PangoCairo.FontMap.get_default()
    for name in ('Monoton.ttf', 'Orbitron.ttf'):
        path = FONTS / name
        if path.exists() and hasattr(font_map, 'add_font_file'):
            try:
                font_map.add_font_file(str(path))
            except GLib.Error:
                pass


def _hex(value, alpha=1.0):
    value = value.lstrip('#')
    return tuple(int(value[i:i+2], 16) / 255 for i in (0, 2, 4)) + (alpha,)


class Backdrop(Gtk.Widget):
    """Full-window sky. The sky, sun and grid columns are painted once into a
    cached texture; only the grid rows move, as cheap GPU rectangles, and only
    while the window is focused."""
    FPS = 15
    CYCLE = 3.6  # seconds per grid row, same pace as Rinse

    def __init__(self, window):
        super().__init__(hexpand=True, vexpand=True, can_target=False)
        self.window = window
        self.phase = 0.0
        self._texture = None
        self._key = None
        # The timer runs only while the sky is actually animating (synthwave look, Animated
        # sky on, window visible and focused); otherwise nothing wakes the CPU (fan-friendly).
        self._timer = 0
        for signal in ('notify::is-active', 'notify::visible'):
            window.connect(signal, lambda *_: self.sync())
        self.connect('unrealize', lambda *_: self.stop())

    def sync(self):
        """Start or stop the animation timer to match the current look and focus."""
        if self._animating():
            if not self._timer:
                self._timer = GLib.timeout_add(1000 // self.FPS, self._tick)
        else:
            self.stop()
        self.queue_draw()

    def stop(self):
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0

    def _animating(self):
        settings = Gtk.Settings.get_default()
        if settings is not None and not settings.get_property('gtk-enable-animations'):
            return False
        prefs = getattr(self.window, 'preference_items', {})
        if prefs.get('glass', True) or not prefs.get('animated_sky', True):
            return False
        return self.window.get_visible() and self.window.is_active()

    def _tick(self):
        if not self._animating():
            self._timer = 0
            return False
        self.phase = (self.phase + 1 / (self.FPS * self.CYCLE)) % 1.0
        self.queue_draw()
        return True

    @staticmethod
    def horizon(h):
        return h * 0.62

    def _paint_static(self, w, h, scale):
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, int(w * scale), int(h * scale))
        cr = cairo.Context(surface)
        cr.scale(scale, scale)
        sky = cairo.LinearGradient(0, 0, 0, h)
        for stop, color in ((0, '#12051f'), (0.45, '#1a0b2e'), (0.72, '#220c3d'), (1, '#2d0f45')):
            sky.add_color_stop_rgba(stop, *_hex(color))
        cr.set_source(sky); cr.paint()
        for cx, cy, radius, color in ((0.12 * w, -0.1 * h, 0.75 * max(w, h), _hex('#9d4dff', 0.30)),
                                      (0.80 * w, 1.05 * h, 0.70 * max(w, h), _hex('#2de2e6', 0.16))):
            glow = cairo.RadialGradient(cx, cy, 0, cx, cy, radius)
            glow.add_color_stop_rgba(0, *color)
            glow.add_color_stop_rgba(1, *color[:3], 0)
            cr.set_source(glow); cr.paint()
        horizon = self.horizon(h)
        radius = min(h * 0.24, w * 0.16, 170)
        sx, sy = w * 0.80, horizon - radius * 0.30
        halo = cairo.RadialGradient(sx, sy, radius * 0.6, sx, sy, radius * 2.0)
        halo.add_color_stop_rgba(0, *PINK, 0.28)
        halo.add_color_stop_rgba(1, *PINK, 0)
        cr.set_source(halo); cr.paint()
        cr.push_group()
        cr.arc(sx, sy, radius, 0, 2 * math.pi)
        sun = cairo.LinearGradient(0, sy - radius, 0, sy + radius)
        for stop, color in ((0, '#ffd166'), (0.35, '#ff9e3d'), (0.75, '#ff2e88'), (1, '#c3127a')):
            sun.add_color_stop_rgba(stop, *_hex(color, 0.55))
        cr.set_source(sun); cr.fill()
        # Rinse's stripes: bands cut through the lower half, thicker toward the bottom.
        cr.set_operator(cairo.OPERATOR_CLEAR)
        for top, bottom in ((0.08, 0.13), (0.26, 0.34), (0.47, 0.58), (0.70, 0.84), (0.92, 1.0)):
            cr.rectangle(sx - radius, sy + radius * top, 2 * radius, radius * (bottom - top))
        cr.fill()
        cr.pop_group_to_source(); cr.paint()
        floor = cairo.LinearGradient(0, horizon, 0, h)
        floor.add_color_stop_rgba(0, *_hex('#1a0830', 0.92))
        floor.add_color_stop_rgba(1, *_hex('#10061d', 0.98))
        cr.rectangle(0, horizon, w, h - horizon); cr.set_source(floor); cr.fill()
        # Columns: pink, fanning out from the vanishing point (static).
        cx, spacing = w / 2, 70
        fade = cairo.LinearGradient(0, horizon, 0, h)
        fade.add_color_stop_rgba(0, *PINK, 0)
        fade.add_color_stop_rgba(0.5, *PINK, 0.42)
        fade.add_color_stop_rgba(1, *PINK, 0.55)
        cr.set_source(fade); cr.set_line_width(1.4)
        count = int(w / spacing) + 4
        for i in range(-count, count + 1):
            cr.move_to(cx + i * spacing * 0.08, horizon); cr.line_to(cx + i * spacing * 3, h)
        cr.stroke()
        line = cairo.LinearGradient(0, 0, w, 0)
        line.add_color_stop_rgba(0, *PINK, 0)
        line.add_color_stop_rgba(0.5, *PINK, 0.9)
        line.add_color_stop_rgba(1, *PINK, 0)
        cr.set_source(line); cr.set_line_width(2)
        cr.move_to(0, horizon); cr.line_to(w, horizon); cr.stroke()
        surface.flush()
        return Gdk.MemoryTexture.new(surface.get_width(), surface.get_height(),
                                     Gdk.MemoryFormat.B8G8R8A8_PREMULTIPLIED,
                                     GLib.Bytes.new(bytes(surface.get_data())), surface.get_stride())

    def do_snapshot(self, snapshot):
        w, h = self.get_width(), self.get_height()
        # Glass: paint nothing, so the frosted desktop shows through (window.glass in style.css).
        if w <= 0 or h <= 0 or getattr(self.window, 'preference_items', {}).get('glass', True):
            return
        scale = self.get_scale_factor()
        if self._key != (w, h, scale):
            self._texture, self._key = self._paint_static(w, h, scale), (w, h, scale)
        snapshot.append_texture(self._texture, Graphene.Rect().init(0, 0, w, h))
        horizon = self.horizon(h)
        depth = h - horizon
        color = Gdk.RGBA()
        for k in range(1, 26):
            d = k - self.phase
            if d < 0.55:
                continue
            y = horizon + depth / d
            if y > h + 2:
                continue
            fade = min(1.0, (y - horizon) / (depth * 0.55))
            color.red, color.green, color.blue, color.alpha = *TEAL, 0.50 * fade
            snapshot.append_color(color, Graphene.Rect().init(0, y - 0.7, w, 1.4))


class ChromeTitle(Gtk.DrawingArea):
    """PHONEBRIDGE in Monoton with Rinse's chrome fill and teal glow, plus a pink tagline."""

    def __init__(self, text='PHONEBRIDGE', tagline='TEXTS FROM YOUR IPHONE', size=24):
        super().__init__(can_target=False)
        self.text, self.tagline, self.size = text, tagline, size
        self.update_property([Gtk.AccessibleProperty.LABEL], [text.title()])
        width, height = self._measure()
        self.set_content_width(width)
        self.set_content_height(height)
        self.set_draw_func(self._draw)

    def _layouts(self, cr_or_context):
        title = PangoCairo.create_layout(cr_or_context)
        title.set_font_description(Pango.FontDescription.from_string(f'Monoton {self.size}px'))
        title.set_text(self.text, -1)
        attrs = Pango.AttrList()
        attrs.insert(Pango.attr_letter_spacing_new(3 * Pango.SCALE))
        title.set_attributes(attrs)
        tag = PangoCairo.create_layout(cr_or_context)
        tag.set_font_description(Pango.FontDescription.from_string('Orbitron Bold 7.5px'))
        tag.set_text(self.tagline, -1)
        tag_attrs = Pango.AttrList()
        tag_attrs.insert(Pango.attr_letter_spacing_new(int(2.6 * Pango.SCALE)))
        tag.set_attributes(tag_attrs)
        return title, tag

    def _measure(self):
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1)
        title, tag = self._layouts(cairo.Context(surface))
        tw, th = title.get_pixel_size()
        gw, gh = tag.get_pixel_size()
        return max(tw, gw) + 16, th + gh + 10

    def _draw(self, _area, cr, w, h):
        title, tag = self._layouts(cr)
        tw, th = title.get_pixel_size()
        gw, _ = tag.get_pixel_size()
        x = (w - tw) / 2
        y = 2
        # Purple drop shadow, then a soft teal glow, then the chrome fill.
        cr.move_to(x, y + 2); PangoCairo.layout_path(cr, title)
        cr.set_source_rgba(*_hex('#5b1c7a')); cr.fill()
        for width, alpha in ((7, 0.10), (4.5, 0.16), (2.5, 0.26)):
            cr.move_to(x, y); PangoCairo.layout_path(cr, title)
            cr.set_source_rgba(*TEAL, alpha); cr.set_line_width(width)
            cr.set_line_join(cairo.LINE_JOIN_ROUND); cr.stroke()
        chrome = cairo.LinearGradient(0, y, 0, y + th)
        for stop, color in ((0, '#ffffff'), (0.36, '#d9fbff'), (0.5, '#3d7aa8'), (0.62, '#8ff7f0'), (1, '#ffe0f0')):
            chrome.add_color_stop_rgba(stop, *_hex(color))
        cr.move_to(x, y); PangoCairo.layout_path(cr, title)
        cr.set_source(chrome); cr.fill()
        tx, ty = (w - gw) / 2, y + th + 3
        cr.move_to(tx, ty); PangoCairo.layout_path(cr, tag)
        cr.set_source_rgba(*PINK, 0.35); cr.set_line_width(2.5); cr.stroke()
        cr.move_to(tx, ty); PangoCairo.layout_path(cr, tag)
        cr.set_source_rgba(*PINK); cr.fill()
