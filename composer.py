"""Spell-checked message composer (Enter reviews, Shift+Enter adds a line break).

A GtkSourceView with libspelling underlines misspelled words and adds
suggestions to the right-click menu. It keeps the old Gtk.Entry contract the
window relies on: at most MAX_TEXT_BYTES characters, Enter to review, Shift+Enter for a new line.
"""
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, GLib, GObject

from model import clean_compose_text
from send_test import MAX_TEXT_BYTES

try:
    gi.require_version('GtkSource', '5')
    gi.require_version('Spelling', '1')
    from gi.repository import GtkSource, Spelling
except (ValueError, ImportError):  # libspelling or GtkSourceView missing: plain composer
    GtkSource = Spelling = None


class Composer(Gtk.ScrolledWindow):
    __gsignals__ = {'changed': (GObject.SignalFlags.RUN_LAST, None, ()),
                    'activate': (GObject.SignalFlags.RUN_LAST, None, ())}

    def __init__(self, placeholder='Write a text…', max_chars=MAX_TEXT_BYTES):
        super().__init__(hexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER,
                         vscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
                         propagate_natural_height=True, max_content_height=132)
        self.add_css_class('composer')
        self.max_chars = max_chars
        self._cleaning = False
        self.spelling = None
        if GtkSource is not None:
            self.buffer = GtkSource.Buffer()
            self.buffer.set_highlight_syntax(False)
            self.buffer.set_highlight_matching_brackets(False)
            self.view = GtkSource.View(buffer=self.buffer)
            try:
                Spelling.init()
                checker = Spelling.Checker.get_default()
                self.spelling = Spelling.TextBufferAdapter.new(self.buffer, checker)
                self.view.set_extra_menu(self.spelling.get_menu_model())
                self.view.insert_action_group('spelling', self.spelling)
                self.spelling.set_enabled(True)
            except (GLib.Error, TypeError, AttributeError):
                self.spelling = None
        else:
            self.buffer = Gtk.TextBuffer()
            self.view = Gtk.TextView(buffer=self.buffer)
        self.view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.view.set_accepts_tab(False)
        self.view.set_top_margin(10); self.view.set_bottom_margin(10)
        self.view.set_left_margin(14); self.view.set_right_margin(14)
        self.view.add_css_class('composer-view')
        self.view.update_property([Gtk.AccessibleProperty.LABEL], ['Message'])
        self.placeholder = Gtk.Label(label=placeholder, xalign=0, can_target=False)
        self.placeholder.add_css_class('composer-placeholder')
        overlay = Gtk.Overlay()
        overlay.set_child(self.view)
        self.placeholder.set_halign(Gtk.Align.START); self.placeholder.set_valign(Gtk.Align.START)
        self.placeholder.set_margin_start(15); self.placeholder.set_margin_top(10)
        overlay.add_overlay(self.placeholder)
        self.set_child(overlay)

        self.buffer.connect('changed', self._changed)
        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect('key-pressed', self._key)
        self.view.add_controller(keys)
        # Right-click puts the caret on the clicked word so suggestions match it.
        click = Gtk.GestureClick(button=Gdk.BUTTON_SECONDARY)
        click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        click.connect('pressed', self._right_click)
        self.view.add_controller(click)

    # ---- Gtk.Entry-compatible surface used by the window ----
    def get_text(self):
        start, end = self.buffer.get_bounds()
        return self.buffer.get_text(start, end, False)

    def set_text(self, text):
        self.buffer.set_text(clean_compose_text(text, self.max_chars))

    def get_position(self):
        return self.buffer.get_iter_at_mark(self.buffer.get_insert()).get_offset()

    def set_position(self, position):
        if position < 0:
            position = self.buffer.get_char_count()
        self.buffer.place_cursor(self.buffer.get_iter_at_offset(position))

    def get_selection_bounds(self):
        bounds = self.buffer.get_selection_bounds()
        if bounds:
            return True, bounds[0].get_offset(), bounds[1].get_offset()
        return False, 0, 0

    def grab_focus(self):
        return self.view.grab_focus()

    # ---- internals ----
    def _changed(self, _buffer):
        if self._cleaning:
            return
        text = self.get_text()
        cleaned = clean_compose_text(text, self.max_chars)
        if cleaned != text:
            position = min(self.get_position(), len(cleaned))
            self._cleaning = True
            self.buffer.set_text(cleaned)
            self._cleaning = False
            self.set_position(position)
        self.placeholder.set_visible(not cleaned)
        self.emit('changed')

    def _key(self, _controller, keyval, _keycode, state):
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_ISO_Enter):
            if not state & Gdk.ModifierType.SHIFT_MASK:
                self.emit('activate')
                return True
            return False  # Shift+Enter: let the view insert a line break
        return False

    def _right_click(self, _gesture, _n, x, y):
        if self.buffer.get_has_selection():
            return
        bx, by = self.view.window_to_buffer_coords(Gtk.TextWindowType.WIDGET, int(x), int(y))
        found, where = self.view.get_iter_at_location(bx, by)
        if found:
            self.buffer.place_cursor(where)
        if self.spelling is not None:
            self.spelling.update_corrections()
