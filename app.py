#!/usr/bin/env python3
"""PhoneBridge desktop prototype. Text-only, local, and explicitly user-driven."""
from datetime import datetime
import os
import threading
from pathlib import Path
import subprocess
import sys
import uuid
import gi
import dbus
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, Gio, GLib, Pango
from dbus.mainloop.glib import DBusGMainLoop
from model import Favorites, Aliases, Preferences, Message, SendGate, readable_time, contact_key, Unread, hide_on_close, insert_emoji, conversation_order, ClearedThreads, find_links, linkify_markup
from composer import Composer
from synthwave import Backdrop, ChromeTitle, register_fonts
import theme
from alerts import Alerts
from history import near_bottom
from send_test import MAX_TEXT_BYTES, make_bmessage, recipient_field

ROOT = Path(__file__).resolve().parent
DEMO = '--demo' in sys.argv


def label(text='', css=None, wrap=False):
    item = Gtk.Label(label=text, xalign=0, wrap=wrap)
    item.set_selectable(wrap)
    if wrap:
        item.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
    if css:
        item.add_css_class(css)
    return item


def button(text, callback, css=None):
    item = Gtk.Button(label=text)
    item.connect('clicked', callback)
    if css:
        item.add_css_class(css)
    return item


def padded(box, size=20):
    for edge in ('top', 'bottom', 'start', 'end'):
        getattr(box, 'set_margin_'+edge)(size)
    return box


class Window(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title='PhoneBridge')
        self.set_default_size(940, 640)
        self.set_size_request(760, 500)
        self.messages = []
        self.unread = Unread()
        try:
            self.cleared_threads = ClearedThreads(memory_only=DEMO)
        except (OSError, ValueError):
            self.cleared_threads = None
        self.quitting = False
        self.thread_rows = {}
        self.link_previews = {}
        self.rendered_peer = None
        self.empty_thread = None
        self.follow_history_latest = True
        self.phones = []
        self.peer = ''
        self.peer_name = ''
        self.connected = False
        self.busy_connecting = False
        self.gate = SendGate()
        self.worker = None
        self.favorites = None
        self.storage_error = None if self.cleared_threads is not None else 'Cleared-thread storage could not be loaded. Deletion is disabled; the existing file has been preserved.'
        self.changing_alert_settings = False
        self.aliases = None
        self.preferences = None
        self.alias_items = {}
        self.preference_items = dict(Preferences.DEFAULTS)
        if DEMO:
            self.favorite_items = {'+15550100101': 'Morgan', '+15550100102': 'Alex'}
        else:
            try:
                self.favorites = Favorites()
                self.favorite_items = self.favorites.items
            except (OSError, ValueError):
                self.storage_error = 'Favorites could not be loaded. Your existing file has been left unchanged.'
                self.favorite_items = {}
        if not DEMO:
            try:
                self.aliases = Aliases()
                self.alias_items = self.aliases.items
            except (OSError, ValueError):
                self.storage_error = 'Aliases could not be loaded. The existing file has been left unchanged.'
            try:
                self.preferences = Preferences()
                self.preference_items = self.preferences.items
            except (OSError, ValueError):
                self.storage_error = 'Notification settings could not be loaded. Alerts are off; existing settings have been preserved.'
        self.alerts = Alerts(lambda text: self.status.set_text(text))
        self.build()
        self.connect('close-request', self.close_requested)
        self.connect('notify::is-active', lambda *_: self.mark_viewed())
        if DEMO:
            self.populate_demo()
        else:
            from bridge import Bridge
            self.worker = Bridge(lambda event, value: GLib.idle_add(self.event, event, value))
            self.worker.command('discover')
        self.apply_look()
        self.render_sidebar()
        if self.storage_error:
            self.status.set_text(self.storage_error)

    def build(self):
        overlay = Gtk.Overlay()
        self.set_child(overlay)
        self.backdrop = Backdrop(self)
        overlay.set_child(self.backdrop)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        overlay.add_overlay(root)
        overlay.set_measure_overlay(root, True)
        header = Gtk.HeaderBar()
        # Two titles: the synthwave chrome, or Vesper's quiet lettering for the glass look.
        self.title_stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.title_stack.add_named(ChromeTitle(), 'synthwave')
        glass_title = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, valign=Gtk.Align.CENTER)
        glass_title.append(label('phonebridge', 'glass-title'))
        glass_title.append(label('texts from your iphone', 'glass-tag'))
        self.title_stack.add_named(glass_title, 'glass')
        header.set_title_widget(self.title_stack)
        self.connection_pill = label('Demo' if DEMO else 'Disconnected', 'connection-pill')
        self.connection_pill.set_valign(Gtk.Align.CENTER)
        header.pack_start(self.connection_pill)
        self.hide_button = button('Hide to bar', lambda _: self.hide_to_bar())
        self.hide_button.set_sensitive(False)
        header.pack_end(self.hide_button)
        self.settings_button = Gtk.MenuButton(icon_name='emblem-system-symbolic', tooltip_text='PhoneBridge settings', valign=Gtk.Align.CENTER)
        self.hide_button.set_valign(Gtk.Align.CENTER)
        self.settings_popover = Gtk.Popover()
        self.settings_button.set_popover(self.settings_popover)
        header.pack_end(self.settings_button)
        root.append(header)
        self.status = label('Open Settings to choose your iPhone and connect.', 'status', True)
        self.status.add_css_class('chat-status')
        self.build_settings()
        split = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        split.set_position(235)
        split.set_vexpand(True)
        root.append(split)
        sidebar = padded(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10), 12)
        sidebar.add_css_class('sidebar')
        split.set_start_child(sidebar)
        split.set_resize_start_child(False)
        split.set_shrink_start_child(False)
        top = Gtk.Box(spacing=8)
        top.append(label('People', 'section-title'))
        spacer = Gtk.Box(hexpand=True); top.append(spacer)
        top.append(button('New', lambda _: self.select_peer('', 'New text')))
        sidebar.append(top)
        self.search = Gtk.SearchEntry(placeholder_text='Name or number')
        self.search.connect('search-changed', lambda _: self.render_sidebar())
        sidebar.append(self.search)
        self.only_favorites = Gtk.CheckButton(label='Favorites only')
        self.only_favorites.connect('toggled', lambda _: self.render_sidebar())
        sidebar.append(self.only_favorites)
        scroller = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.people = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.people.add_css_class('people')
        scroller.set_child(self.people)
        sidebar.append(scroller)
        sidebar.append(label('Local aliases & favorites', 'footnote'))
        pane = padded(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=9), 14)
        split.set_end_child(pane)
        title_row = Gtk.Box(spacing=8)
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, hexpand=True)
        self.heading = label('Your texts, close by.', 'chat-title')
        self.heading.set_ellipsize(Pango.EllipsizeMode.END)
        self.heading.set_max_width_chars(26)
        self.subheading = label('Choose a person or start a text.', 'muted', True)
        titles.append(self.heading); titles.append(self.subheading)
        title_row.append(titles)
        self.star = button('☆', self.toggle_favorite)
        self.star.set_tooltip_text('Add or remove this person from favorites')
        self.star.set_sensitive(False)
        title_row.append(self.star)
        self.alias_button = button('Edit name', self.edit_alias)
        self.alias_button.set_tooltip_text('Give this number a local alias')
        title_row.append(self.alias_button)
        self.delete_button = button('Delete thread', self.delete_thread)
        self.delete_button.set_tooltip_text('Clear this conversation from PhoneBridge only')
        title_row.append(self.delete_button)
        for control in (self.star, self.alias_button, self.delete_button):
            control.set_valign(Gtk.Align.CENTER)
        pane.append(title_row)
        self.latest_button = button('Jump to latest ↓', self.jump_latest)
        self.latest_button.set_halign(Gtk.Align.END)
        self.latest_button.set_visible(False)
        pane.append(self.latest_button)
        self.thread_scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.thread = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, valign=Gtk.Align.END)
        self.auto_scrolling = False
        self.scroll_geometry = (0, 0)
        self.thread_scroll.set_child(self.thread)
        # Measure the thread at its natural height, so the scroll range covers every line
        # (the default "minimum" policy left the newest text partly below the window).
        self.thread_scroll.get_child().set_vscroll_policy(Gtk.ScrollablePolicy.NATURAL)
        pane.append(self.thread_scroll)
        adjustment = self.thread_scroll.get_vadjustment()
        adjustment.connect('value-changed', self.history_scrolled)
        adjustment.connect('changed', self.history_resized)
        recipient_row = Gtk.Box(spacing=8)
        recipient_row.append(label('To', 'muted'))
        self.recipient = Gtk.Entry(placeholder_text='+country-code number or Apple-ID email', hexpand=True)
        self.recipient.set_tooltip_text('One recipient only. Incoming group texts target the sender, not the group.')
        self.recipient.connect('changed', self.recipient_changed)
        recipient_row.append(self.recipient)
        pane.append(recipient_row)
        compose_row = Gtk.Box(spacing=8)
        self.compose = Composer('Write a text…')
        self.compose.connect('changed', lambda _: self.update_controls())
        self.compose.connect('activate', lambda _: self.review(None))
        compose_row.append(self.compose)
        self.emoji_button = Gtk.MenuButton(label='😊', valign=Gtk.Align.END)
        self.emoji_button.set_tooltip_text('Insert an emoji')
        self.emoji_popover = Gtk.Popover()
        emoji_grid = Gtk.Grid(column_spacing=4, row_spacing=4)
        padded(emoji_grid, 10)
        emojis = [('😊', 'Smile'), ('😂', 'Laugh'), ('🥰', 'Feeling loved'), ('😘', 'Kiss'),
                  ('❤️', 'Red heart'), ('♥', 'Heart'), ('💕', 'Two hearts'), ('💔', 'Broken heart'),
                  ('👍', 'Thumbs up'), ('👎', 'Thumbs down'), ('🙏', 'Thank you'), ('👋', 'Wave'),
                  ('🎉', 'Celebrate'), ('🎂', 'Birthday'), ('☀️', 'Sunshine'), ('🌹', 'Rose'),
                  ('😢', 'Sad'), ('😮', 'Surprised'), ('😉', 'Wink'), ('😎', 'Cool')]
        for index, (emoji, name) in enumerate(emojis):
            choice = button(emoji, lambda _, value=emoji: self.add_emoji(value))
            choice.set_tooltip_text(name)
            choice.update_property([Gtk.AccessibleProperty.LABEL], [name])
            emoji_grid.attach(choice, index % 4, index // 4, 1, 1)
        self.emoji_popover.set_child(emoji_grid)
        self.emoji_button.set_popover(self.emoji_popover)
        compose_row.append(self.emoji_button)
        self.send_button = button('Review →', self.review, 'suggested-action')
        self.send_button.set_valign(Gtk.Align.END)
        compose_row.append(self.send_button)
        pane.append(compose_row)
        self.compose_hint = label(f'0 / {MAX_TEXT_BYTES} UTF-8 bytes · Shift+Enter for a new line', 'footnote', True)
        pane.append(self.compose_hint)
        self.resolve_button = button('I checked my iPhone', self.resolve)
        self.resolve_button.set_visible(False)
        self.resolve_button.set_halign(Gtk.Align.END)
        pane.append(self.resolve_button)
        pane.append(self.status)
        self.render_thread()
        self.update_controls()

    def build_settings(self):
        box = padded(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12), 18)
        box.set_size_request(370, -1)
        settings_scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, propagate_natural_height=True, max_content_height=500)
        settings_scroll.set_child(box)
        self.settings_popover.set_child(settings_scroll)
        box.append(label('PhoneBridge settings', 'section-title'))
        box.append(label('IPHONE CONNECTION', 'eyebrow'))
        self.phone_choice = Gtk.DropDown.new_from_strings(['Looking for paired phones…'])
        box.append(self.phone_choice)
        row = Gtk.Box(spacing=8)
        self.refresh_button = button('Refresh', lambda _: self.refresh_devices())
        self.connect_button = button('Connect', self.connect_phone, 'suggested-action')
        self.connect_button.set_sensitive(False)
        row.append(self.refresh_button); row.append(self.connect_button)
        if not DEMO:
            self.setup_button = button('Pair / setup…', self.setup)
            row.append(self.setup_button)
        box.append(row)
        box.append(label('NOTIFICATIONS', 'eyebrow'))
        notify_row = Gtk.Box(spacing=10)
        notify_row.append(label('Notifications', 'muted'))
        self.notifications = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.notifications.set_active(self.preference_items['notifications_enabled'])
        notify_row.append(self.notifications)
        notify_row.append(label('Sound', 'muted'))
        self.sound = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.sound.set_active(self.preference_items['sound_enabled'])
        notify_row.append(self.sound)
        box.append(notify_row)
        self.test_sound = button('Test ding', self.preview_sound)
        self.test_sound.set_halign(Gtk.Align.START)
        box.append(self.test_sound)
        self.notifications.connect('notify::active', self.alert_settings_changed)
        self.sound.connect('notify::active', self.alert_settings_changed)
        box.append(label('WINDOW & STATUS BAR', 'eyebrow'))
        modes = Gtk.Box(spacing=10)
        modes.append(label('Live in status bar', 'muted'))
        self.tray_switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.tray_switch.set_active(self.preference_items['tray_enabled'])
        modes.append(self.tray_switch)
        box.append(modes)
        compact = Gtk.Box(spacing=10)
        compact.append(label('Compact floating window', 'muted'))
        self.compact_switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.compact_switch.set_active(self.preference_items['compact_window'])
        compact.append(self.compact_switch)
        box.append(compact)
        glass = Gtk.Box(spacing=10)
        glass.append(label('Glass (see-through)', 'muted'))
        self.glass_switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.glass_switch.set_active(self.preference_items.get('glass', True))
        self.glass_switch.set_tooltip_text('Frosted glass in the calm Vesper style, in the colors of your Omarchy theme. Off brings back the synthwave sky.')
        glass.append(self.glass_switch)
        box.append(glass)
        self.glass_switch.connect('notify::active', self.glass_setting_changed)
        sky = Gtk.Box(spacing=10)
        sky.append(label('Animated sky', 'muted'))
        self.sky_switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.sky_switch.set_active(self.preference_items.get('animated_sky', True))
        self.sky_switch.set_tooltip_text('The neon grid drifts while PhoneBridge is focused. Turn off to save battery.')
        sky.append(self.sky_switch)
        box.append(sky)
        self.sky_switch.connect('notify::active', self.sky_setting_changed)
        self.tray_switch.connect('notify::active', self.mode_settings_changed)
        self.compact_switch.connect('notify::active', self.mode_settings_changed)
        box.append(label('Closing hides the chat when a tray icon is available. Messaging keeps running. Turn compact mode off for a normal workspace window.', 'muted', True))
        box.append(button('Quit PhoneBridge', lambda _: self.request_quit()))

    def refresh_devices(self):
        if self.worker:
            self.refresh_button.set_sensitive(False)
            self.status.set_text('Checking paired phones…')
            self.worker.command('discover')

    def connect_phone(self, _):
        if self.gate.state != 'idle' or not self.worker:
            return
        if self.connected:
            self.busy_connecting = True
            self.worker.command('disconnect')
        else:
            index = self.phone_choice.get_selected()
            if index >= len(self.phones):
                return
            self.busy_connecting = True
            self.worker.command('connect', self.phones[index])
        self.update_controls()

    def setup(self, _):
        try:
            subprocess.Popen(['xdg-terminal-exec', sys.executable, str(ROOT/'connect_phone.py'), '--hold'])
            self.status.set_text('Follow the connection guide in the new terminal. When it finishes, click Refresh here, then Connect.')
        except OSError:
            self.status.set_text('Open a terminal and run: python '+str(ROOT/'connect_phone.py'))

    def event(self, event, value):
        if event == 'stopped':
            if self.quitting:
                self.get_application().finish_quit()
            else:
                self.worker = None
                self.connected = False
                self.status.set_text('Bluetooth worker stopped. Quit and reopen PhoneBridge to reconnect.')
                self.update_controls()
            return False
        if event == 'reset':
            self.messages = []
            self.unread = Unread()
            self.select_peer('', 'New text')
            self.compose.set_text('')
            self.render_sidebar()
        elif event == 'devices':
            self.phones = value
            self.phone_choice.set_model(Gtk.StringList.new([p['name'] for p in value] or ['No paired messaging phone found']))
            self.refresh_button.set_sensitive(True)
            self.status.set_text('Choose your iPhone and connect.' if value else 'Pair your iPhone first, then Refresh. Use iPhone access if the message-permission switch is missing.')
        elif event == 'connecting':
            self.connected = False
            self.status.set_text('Connecting to '+value+'…')
        elif event == 'connected':
            self.connected = True
            self.busy_connecting = False
            self.status.set_text('Connected to '+value+'.')
            self.settings_popover.popdown()
            self.render_thread()
            self.request_bodies()
        elif event == 'disconnected':
            self.connected = self.busy_connecting = False
            self.status.set_text('Disconnected. Texts remain visible until you close PhoneBridge.')
        elif event == 'error':
            self.connected = self.busy_connecting = False
            self.refresh_button.set_sensitive(True)
            self.status.set_text('Connection unavailable ('+value+'). Check Bluetooth and the iPhone message permission, then reconnect.')
        elif event == 'messages':
            known = {m.key for m in self.messages}
            fresh = [m for m in value['items'] if m.key not in known
                     and (self.cleared_threads is None or self.cleared_threads.visible(m))]
            self.messages.extend(fresh)
            viewed = contact_key(self.peer) if self.get_visible() and self.is_active() and self.follow_history_latest else None
            self.unread.incoming(fresh, value['initial'], viewed)
            if len(self.messages) > 1000:
                self.messages = self.messages[-1000:]
            if fresh:
                self.render_sidebar(); self.render_thread()
                self.request_bodies()
            if not DEMO:
                self.alerts.incoming(value['initial'], len(fresh), self.notifications.get_active(), self.sound.get_active())
        elif event == 'body':
            for item in self.messages:
                if item.key == value['key']:
                    item.body_state = value['state']
                    if value['text'] is not None:
                        item.text = value['text']
                    break
            self.render_thread()
        elif event == 'sent':
            for item in self.messages:
                if item.key == value['id']:
                    item.status = value['state']
            self.gate.finish(value['state'])
            self.status.set_text(value['detail'])
            if value['state'] == 'accepted':
                self.compose.set_text('')
            self.render_thread(); self.render_sidebar()
        self.update_controls()
        if event == 'sent' and value['state'] == 'accepted':
            self.compose.grab_focus()
        self.get_application().refresh_tray()
        return False

    def render_sidebar(self):
        while child := self.people.get_first_child():
            self.people.remove(child)
        peers = {contact_key(a): (a, self.display_name(a, n)) for a, n in self.favorite_items.items()}
        favorite_keys = {contact_key(a) for a in self.favorite_items}
        for message in self.messages:
            if message.address:
                peers.setdefault(contact_key(message.address), (message.address, self.display_name(message.address, message.name)))
        active_keys = {contact_key(m.address) for m in self.messages}
        if self.cleared_threads:
            peers = {k: v for k, v in peers.items()
                     if k in active_keys or not self.cleared_threads.cleared(v[0])}
        query = self.search.get_text().casefold()
        shown = 0
        for key, (address, name) in conversation_order(peers, self.messages):
            if self.only_favorites.get_active() and key not in favorite_keys:
                continue
            if query and query not in (name+' '+address).casefold():
                continue
            content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
            unread = self.unread.count(address)
            display = ('★  ' if key in favorite_keys else '')+name+(f'  · {unread}' if unread else '')
            person_label = label(display, 'person-name')
            person_label.set_ellipsize(Pango.EllipsizeMode.END)
            person_label.set_width_chars(1)
            person_label.set_max_width_chars(24)
            person_label.set_tooltip_text(display)
            content.append(person_label)
            content.append(label(address, 'muted'))
            entry = Gtk.Button(child=content)
            entry.add_css_class('person')
            if self.peer and key == contact_key(self.peer):
                entry.add_css_class('selected')
            if unread:
                entry.add_css_class('unread')
            entry.connect('clicked', lambda _, a=address, n=name: self.select_peer(a, n))
            self.people.append(entry)
            shown += 1
        if not shown:
            self.people.append(label('No favorites yet.' if self.only_favorites.get_active() else 'Your incoming senders will appear here.\nUse New text to compose.', 'muted', True))

    def select_peer(self, address, name):
        if self.gate.state == 'pending':
            return
        self.peer = address
        self.peer_name = self.display_name(address, name)
        self.recipient.set_text(address)
        self.heading.set_text(self.peer_name)
        self.subheading.set_text(address or 'Enter one phone number or Apple-ID email below.')
        self.render_thread(force_bottom=True)
        self.render_sidebar()
        self.request_bodies()
        self.mark_viewed()
        self.update_controls()

    def recipient_changed(self, _):
        address = self.recipient.get_text().strip()
        if address != self.peer:
            self.peer = address
            self.peer_name = self.display_name(address, self.source_name(address))
            self.heading.set_text(self.peer_name or 'New text')
            self.subheading.set_text(address or 'Enter one phone number or Apple-ID email below.')
            self.render_thread(force_bottom=True)
            self.request_bodies()
        self.update_controls()

    def request_bodies(self):
        if DEMO or not self.worker or not self.connected:
            return
        wanted = []
        changed_states = False
        for message in self.messages:
            if (not message.outgoing and contact_key(message.address) == contact_key(self.peer)
                    and message.body_state in ('preview', 'loading')):
                if message.body_state != 'loading':
                    message.body_state = 'loading'
                    changed_states = True
                wanted.append(message.key)
        # Replacing the batch stops fetching the former person's remaining
        # messages when the user selects someone else. Sends take priority.
        self.worker.command('bodies', wanted)
        if changed_states:
            self.render_thread()

    def retry_body(self, message):
        message.body_state = 'preview'
        self.request_bodies()
        self.render_thread()

    def render_thread(self, force_bottom=False):
        peer_key = contact_key(self.peer)
        changed_peer = self.rendered_peer != peer_key
        if changed_peer:
            self.rendered_peer = peer_key
            self.thread_rows = {}
            self.empty_thread = None
            while child := self.thread.get_first_child():
                self.thread.remove(child)
        adjustment = self.thread_scroll.get_vadjustment()
        follow = force_bottom or changed_peer or near_bottom(adjustment.get_value(), adjustment.get_upper(), adjustment.get_page_size())
        self.follow_history_latest = follow
        items = [m for m in self.messages if contact_key(m.address) == peer_key] if self.peer else []
        if not items:
            if self.empty_thread is None:
                empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, valign=Gtk.Align.CENTER, vexpand=True)
                empty.append(label('A bridge, not another account.', 'empty-title'))
                empty.append(label('Use your nearby iPhone to receive and send texts here.\nNo Mac relay. No Apple sign-in on Linux.', 'muted', True))
                self.thread.append(empty)
                self.empty_thread = empty
            return
        if self.empty_thread is not None:
            self.thread.remove(self.empty_thread)
            self.empty_thread = None
        active_keys = {message.key for message in items}
        for key in set(self.thread_rows)-active_keys:
            self.thread.remove(self.thread_rows.pop(key)['bubble'])
        for message in items:
            if message.key not in self.thread_rows:
                bubble = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, hexpand=True)
                bubble.add_css_class('outgoing' if message.outgoing else 'incoming')
                bubble.set_halign(Gtk.Align.FILL)
                text = label('', 'message-text', True)
                text.set_width_chars(1)
                text.set_max_width_chars(80)
                text.set_hexpand(True)
                meta = label('', 'message-meta', True)
                meta.set_width_chars(1)
                meta.set_max_width_chars(80)
                more = button('Load full text', lambda _, m=message: self.retry_body(m))
                more.set_halign(Gtk.Align.START)
                links = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
                bubble.append(text); bubble.append(links); bubble.append(meta); bubble.append(more)
                self.thread.append(bubble)
                self.thread_rows[message.key] = {'bubble': bubble, 'text': text, 'meta': meta, 'more': more, 'links': links}
            row = self.thread_rows[message.key]
            if row.get('raw') != message.text:
                row['raw'] = message.text
                row['text'].set_markup(linkify_markup(message.text))
                self.render_links(row['links'], message.text)
            meta_text = readable_time(message.when)
            if message.status:
                meta_text += ' · '+{'pending': 'Sending…', 'accepted': 'Accepted by iPhone', 'uncertain': 'Check iPhone · outcome uncertain'}.get(message.status, message.status)
            elif message.body_state != 'full':
                meta_text += ' · '+{'preview': 'Text preview', 'loading': 'Loading full text…', 'unavailable': 'Preview only · full text unavailable'}.get(message.body_state, '')
            if row['meta'].get_text() != meta_text:
                row['meta'].set_text(meta_text)
            row['more'].set_visible(not message.outgoing and message.body_state in ('preview', 'unavailable'))
            row['more'].set_sensitive(self.connected)
        self.latest_button.set_visible(not follow)
        if follow:
            GLib.idle_add(self.scroll_bottom)

    def render_links(self, box, text):
        """A chip per link (max 3). Preview fetches title and thumbnail only when clicked."""
        while child := box.get_first_child():
            box.remove(child)
        seen = []
        for _start, _end, url in find_links(text):
            if url not in seen:
                seen.append(url)
        for url in seen[:3]:
            slot = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            box.append(slot)
            self.fill_link_slot(slot, url)

    def fill_link_slot(self, slot, url):
        while child := slot.get_first_child():
            slot.remove(child)
        state = self.link_previews.get(url)
        if isinstance(state, dict):
            slot.append(self.link_card(url, state))
            return
        from urllib.parse import urlparse
        host = (urlparse(url).hostname or url).removeprefix('www.')
        chip = Gtk.Box(spacing=8)
        chip.add_css_class('link-chip')
        name = label('🔗  '+host, 'link-host')
        name.set_ellipsize(Pango.EllipsizeMode.END)
        name.set_hexpand(True)
        chip.append(name)
        if state == 'loading':
            spinner = Gtk.Spinner(spinning=True)
            chip.append(spinner)
        else:
            preview = button('Preview', lambda _: self.load_preview(slot, url), 'chip-button')
            preview.set_tooltip_text('Fetch this page\'s title and picture (connects to '+host+')')
            chip.append(preview)
            if state == 'failed':
                chip.append(label('No preview', 'link-note'))
        chip.append(button('Open ↗', lambda _: self.open_link(url), 'chip-button'))
        slot.append(chip)

    def link_card(self, url, info):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        card.add_css_class('link-card')
        if info.get('texture') is not None:
            picture = Gtk.Picture.new_for_paintable(info['texture'])
            picture.set_content_fit(Gtk.ContentFit.COVER)
            picture.set_can_shrink(True)
            picture.set_size_request(-1, 170)
            picture.add_css_class('link-image')
            if info.get('is_video'):
                stack = Gtk.Overlay()
                stack.set_child(picture)
                play = label('▶', 'play-badge')
                play.set_halign(Gtk.Align.CENTER); play.set_valign(Gtk.Align.CENTER)
                stack.add_overlay(play)
                card.append(stack)
            else:
                card.append(picture)
        body = padded(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4), 12)
        site = label((info.get('site') or '').upper(), 'link-site')
        site.set_ellipsize(Pango.EllipsizeMode.END)
        body.append(site)
        title = label(info.get('title') or url, 'link-title', True)
        title.set_selectable(False)
        title.set_lines(2); title.set_ellipsize(Pango.EllipsizeMode.END)
        body.append(title)
        if info.get('description'):
            description = label(info['description'], 'link-description', True)
            description.set_selectable(False)
            description.set_lines(2); description.set_ellipsize(Pango.EllipsizeMode.END)
            body.append(description)
        action = button('Watch ▶' if info.get('is_video') else 'Open ↗', lambda _: self.open_link(url), 'link-open')
        action.set_halign(Gtk.Align.START)
        action.set_margin_top(6)
        body.append(action)
        card.append(body)
        return card

    def load_preview(self, slot, url):
        if self.link_previews.get(url) == 'loading':
            return
        self.link_previews[url] = 'loading'
        self.fill_link_slot(slot, url)

        def work():
            try:
                from linkpreview import fetch_preview
                info = fetch_preview(url)
            except Exception:
                info = None
            GLib.idle_add(done, info)

        def done(info):
            if info is None:
                self.link_previews[url] = 'failed'
            else:
                texture = None
                if info.get('image'):
                    try:
                        texture = Gdk.Texture.new_from_bytes(GLib.Bytes.new(info['image']))
                    except GLib.Error:
                        texture = None
                info = {k: v for k, v in info.items() if k != 'image'}
                info['texture'] = texture
                self.link_previews[url] = info
            if slot.get_parent() is not None:
                self.fill_link_slot(slot, url)
            return False

        threading.Thread(target=work, daemon=True).start()

    def open_link(self, url):
        Gtk.UriLauncher.new(url).launch(self, None, None, None)

    def history_scrolled(self, adjustment):
        # Only a real scroll changes whether we follow the newest text. Moves we make
        # ourselves, and moves caused by the page growing or the window resizing, don't.
        geometry = (adjustment.get_upper(), adjustment.get_page_size())
        if self.auto_scrolling or geometry != self.scroll_geometry:
            self.scroll_geometry = geometry
            if self.follow_history_latest:
                self.queue_scroll_bottom()
            return
        self.follow_history_latest = near_bottom(adjustment.get_value(), adjustment.get_upper(), adjustment.get_page_size())
        self.latest_button.set_visible(not self.follow_history_latest)
        self.mark_viewed()

    def history_resized(self, adjustment):
        self.scroll_geometry = (adjustment.get_upper(), adjustment.get_page_size())
        if self.follow_history_latest:
            # Wait for the layout pass to finish; a move made during it isn't drawn.
            self.queue_scroll_bottom()

    def queue_scroll_bottom(self):
        if not getattr(self, 'scroll_pending', False):
            self.scroll_pending = True
            def run():
                self.scroll_pending = False
                self.scroll_bottom()
                return False
            GLib.idle_add(run, priority=GLib.PRIORITY_LOW)

    def show_latest(self):
        """Opening the window always lands on the newest text, once the layout settles."""
        self.follow_history_latest = True
        for delay in (0, 120, 400):
            GLib.timeout_add(delay, self.scroll_bottom)

    def jump_latest(self, _):
        self.follow_history_latest = True
        self.scroll_bottom()
        self.mark_viewed()

    def scroll_bottom(self):
        if self.follow_history_latest:
            adjustment = self.thread_scroll.get_vadjustment()
            self.auto_scrolling = True
            try:
                adjustment.set_value(max(0, adjustment.get_upper()-adjustment.get_page_size()))
            finally:
                self.auto_scrolling = False
            self.latest_button.set_visible(False)
        return False

    def display_name(self, address, fallback=''):
        return self.alias_items.get(contact_key(address), fallback or address)

    def source_name(self, address):
        key = contact_key(address)
        for message in reversed(self.messages):
            if not message.outgoing and contact_key(message.address) == key:
                return message.name
        return next((name for a, name in self.favorite_items.items() if contact_key(a) == key), address)

    def favorite_address(self, address):
        return next((a for a in self.favorite_items if contact_key(a) == contact_key(address)), None)

    def delete_thread(self, _):
        if self.gate.state != 'idle' or self.quitting or not self.peer or self.cleared_threads is None:
            return
        address = self.peer
        # Snapshot the displayed history: texts arriving during confirmation survive.
        snapshot = list(self.messages)
        dialog = Gtk.Window(title='Delete PhoneBridge thread?', transient_for=self, modal=True, default_width=420)
        box = padded(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14), 24)
        dialog.set_child(box)
        box.append(label('Delete this thread?', 'chat-title'))
        box.append(label(self.display_name(address), None, True))
        box.append(label('Clears these texts from PhoneBridge only, including after reopening. Messages on your iPhone, aliases and favorites are kept. New texts will bring the conversation back. This cannot be undone here.', 'muted', True))
        error = label('', 'muted', True)
        box.append(error)
        actions = Gtk.Box(spacing=12)
        actions.append(button('Cancel', lambda _: dialog.destroy()))
        def confirm(_):
            if self.gate.state != 'idle' or self.quitting:
                dialog.destroy()
                return
            try:
                self.cleared_threads.clear(address, snapshot)
            except (OSError, ValueError):
                error.set_text('Could not save the deletion. The thread has been kept.')
                return
            self.messages = [m for m in self.messages if self.cleared_threads.visible(m)]
            unread_key = contact_key(address)
            deleted_keys = {m.key for m in snapshot if contact_key(m.address) == unread_key}
            if unread_key in self.unread.items:
                self.unread.items[unread_key].difference_update(deleted_keys)
            if self.worker:
                self.worker.command('bodies', [])
            self.select_peer('', 'New text')
            self.render_sidebar()
            self.get_application().refresh_tray()
            self.status.set_text('Thread deleted from PhoneBridge. iPhone messages are unchanged.')
            dialog.destroy()
        actions.append(button('Delete thread', confirm, 'destructive-action'))
        box.append(actions)
        dialog.present()

    def edit_alias(self, _):
        address = self.peer
        if not address:
            return
        dialog = Gtk.Window(title='Name this number', transient_for=self, modal=True, default_width=420)
        box = padded(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14), 24)
        dialog.set_child(box)
        box.append(label('A familiar name', 'chat-title'))
        box.append(label(address, 'muted', True))
        entry = Gtk.Entry(placeholder_text='For example: Family or Work', max_length=200)
        entry.set_text(self.alias_items.get(contact_key(address), ''))
        box.append(entry)
        box.append(label('Used in People, favorites, and this heading. The phone number stays visible and is never changed. Clear the name to remove the alias.', 'muted', True))
        error = label('', 'muted', True); box.append(error)
        actions = Gtk.Box(spacing=12)
        actions.append(button('Cancel', lambda _: dialog.destroy()))
        def save(_):
            try:
                if DEMO:
                    name = entry.get_text().strip()
                    if name:
                        self.alias_items[contact_key(address)] = name
                    else:
                        self.alias_items.pop(contact_key(address), None)
                elif self.aliases:
                    self.aliases.set_name(address, entry.get_text())
                    self.alias_items = self.aliases.items
                else:
                    raise ValueError('Alias storage is unavailable. Existing data is preserved.')
            except (ValueError, OSError):
                error.set_text('The alias could not be saved. Check the name and local storage.')
                return
            self.peer_name = self.display_name(self.peer, self.source_name(self.peer))
            self.heading.set_text(self.peer_name or 'New text')
            self.render_sidebar()
            self.status.set_text('Name saved locally.' if entry.get_text().strip() else 'Local alias removed.')
            dialog.destroy()
        actions.append(button('Save name', save, 'suggested-action'))
        box.append(actions)
        entry.connect('activate', save)
        dialog.present()

    def toggle_favorite(self, _):
        existing = self.favorite_address(self.peer)
        if not self.favorites:
            if DEMO:
                if existing:
                    del self.favorite_items[existing]
                else:
                    self.favorite_items[self.peer] = self.source_name(self.peer)
            else:
                self.status.set_text('Favorites storage is unavailable. Existing data has been preserved.')
                return
        else:
            try:
                self.favorites.toggle(existing or self.peer, self.source_name(self.peer))
                self.favorite_items = self.favorites.items
            except (OSError, ValueError):
                self.status.set_text('Favorite could not be saved. Check the address and local storage.')
                return
        self.render_sidebar(); self.update_controls()

    def alert_settings_changed(self, *_):
        if self.changing_alert_settings:
            return
        enabled, sound = self.notifications.get_active(), self.sound.get_active()
        if DEMO:
            self.preference_items = {'notifications_enabled': enabled, 'sound_enabled': sound}
        elif self.preferences:
            try:
                self.preferences.set(enabled, sound)
                self.preference_items = self.preferences.items
            except OSError:
                # Restore the last persisted choice if the write failed.
                self.changing_alert_settings = True
                try:
                    self.notifications.set_active(self.preference_items['notifications_enabled'])
                    self.sound.set_active(self.preference_items['sound_enabled'])
                finally:
                    self.changing_alert_settings = False
                self.status.set_text('Notification choices could not be saved. Previous settings restored.')
        self.update_controls()

    def preview_sound(self, _):
        if not DEMO and self.notifications.get_active() and self.sound.get_active():
            self.alerts.play_sound()

    def update_controls(self):
        pending = self.gate.state == 'pending' or self.quitting
        self.recipient.set_sensitive(not pending)
        self.compose.set_sensitive(self.gate.state == 'idle' and not self.quitting)
        self.emoji_button.set_sensitive(self.gate.state == 'idle' and not self.quitting)
        self.phone_choice.set_sensitive(not self.connected and not self.busy_connecting and not pending)
        self.connect_button.set_label('Disconnect' if self.connected else 'Connect')
        self.connect_button.set_sensitive(not DEMO and bool(self.phones) and not self.busy_connecting and self.gate.state == 'idle')
        self.refresh_button.set_sensitive(not DEMO and not self.connected and not self.busy_connecting and not pending)
        try:
            make_bmessage(self.recipient.get_text().strip(), self.compose.get_text())
            valid = True
        except ValueError:
            valid = False
        length = len(self.compose.get_text().encode('utf-8'))
        self.compose_hint.set_text(f'{length} / {MAX_TEXT_BYTES} UTF-8 bytes · Shift+Enter for a new line' + (' · shorten this text to send' if length > MAX_TEXT_BYTES else ''))
        self.send_button.set_sensitive(self.connected and valid and self.gate.state == 'idle' and not DEMO and not self.quitting and self.worker is not None)
        if not DEMO:
            self.setup_button.set_sensitive(not self.connected and not self.busy_connecting and not pending)
        self.delete_button.set_sensitive(bool(self.peer) and self.gate.state == 'idle' and not self.quitting and self.cleared_threads is not None)
        self.star.set_sensitive(bool(self.peer) and not pending)
        self.star.set_label('★' if self.favorite_address(self.peer) else '☆')
        try:
            recipient_field(self.peer)
            can_alias = True
        except ValueError:
            can_alias = False
        self.alias_button.set_sensitive(can_alias and not pending and (DEMO or self.aliases is not None))
        self.notifications.set_sensitive(DEMO or self.preferences is not None)
        self.sound.set_sensitive(self.notifications.get_active() and (DEMO or self.preferences is not None))
        self.test_sound.set_sensitive(not DEMO and self.notifications.get_active() and self.sound.get_active())
        self.resolve_button.set_visible(self.gate.state == 'uncertain')
        self.hide_button.set_sensitive(self.preference_items['tray_enabled'] and self.get_application().tray_ready)
        self.connection_pill.set_text('Demo' if DEMO else 'Connected' if self.connected else 'Connecting…' if self.busy_connecting else 'Disconnected')
        self.tray_switch.set_sensitive(DEMO or self.preferences is not None)
        self.compact_switch.set_sensitive(DEMO or self.preferences is not None)

    def add_emoji(self, emoji):
        if self.gate.state != 'idle' or self.quitting:
            self.emoji_popover.popdown()
            return
        try:
            text, position = insert_emoji(self.compose.get_text(), emoji,
                                          self.compose.get_position(),
                                          self.compose.get_selection_bounds())
        except ValueError as error:
            self.status.set_text(str(error))
        else:
            self.compose.set_text(text)
            self.compose.grab_focus()
            self.compose.set_position(position)
        self.emoji_popover.popdown()

    def review(self, _):
        if not self.send_button.get_sensitive():
            return
        address, text = self.recipient.get_text().strip(), self.compose.get_text()
        dialog = Gtk.Window(title='Review your text', transient_for=self, modal=True, default_width=460)
        box = padded(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16), 24)
        dialog.set_child(box)
        box.append(label('Ready to send?', 'chat-title'))
        box.append(label('TO ONE RECIPIENT', 'eyebrow'))
        alias = self.display_name(address)
        if alias != address:
            box.append(label(alias, None, True))
        box.append(label(address, None, True))
        box.append(label(text, 'review-text', True))
        box.append(label('This sends to this address only. Group members are not included. Your iPhone chooses iMessage or SMS.', 'muted', True))
        actions = Gtk.Box(spacing=12)
        def keep_editing(*_):
            dialog.destroy()
            self.compose.grab_focus()
        actions.append(button('Keep editing', keep_editing))
        keys = Gtk.EventControllerKey()
        def review_key(_, keyval, keycode, state):
            if keyval == Gdk.KEY_Escape:
                keep_editing()
                return True
            return False
        keys.connect('key-pressed', review_key)
        dialog.add_controller(keys)
        def confirm(_):
            if self.gate.state != 'idle' or not self.connected:
                dialog.destroy()
                return
            self.gate.begin()
            key = str(uuid.uuid4())
            self.messages.append(Message(key, address, self.peer_name or address, text,
                datetime.now().strftime('%Y%m%dT%H%M%S'), True, 'pending', 'full'))
            self.status.set_text('Sending once through your iPhone…')
            self.worker.command('send', {'id': key, 'address': address, 'text': text})
            dialog.destroy()
            self.render_thread(force_bottom=True); self.render_sidebar(); self.update_controls()
        confirm_button = button('Send text', confirm, 'suggested-action')
        confirm_button.set_receives_default(True)
        actions.append(confirm_button)
        dialog.set_default_widget(confirm_button)
        box.append(actions)
        dialog.present()
        confirm_button.grab_focus()

    def resolve(self, _):
        self.gate.acknowledge()
        self.compose.set_text('')
        self.status.set_text('Previous outcome acknowledged. Compose a new text when ready.')
        self.update_controls()

    def mark_viewed(self):
        if (self.get_visible() and self.is_active() and self.follow_history_latest
                and self.peer and self.unread.count(self.peer)):
            self.unread.read(self.peer)
            self.render_sidebar()
            self.get_application().refresh_tray()

    def mode_settings_changed(self, *_):
        if self.changing_alert_settings:
            return
        tray, compact = self.tray_switch.get_active(), self.compact_switch.get_active()
        try:
            if not DEMO and self.preferences:
                self.preferences.set(self.notifications.get_active(), self.sound.get_active(), tray=tray, compact=compact)
                self.preference_items = self.preferences.items
            else:
                self.preference_items = {**self.preference_items, 'tray_enabled': tray, 'compact_window': compact}
        except OSError:
            self.changing_alert_settings = True
            try:
                self.tray_switch.set_active(self.preference_items['tray_enabled'])
                self.compact_switch.set_active(self.preference_items['compact_window'])
            finally:
                self.changing_alert_settings = False
            self.status.set_text('Window settings could not be saved. Previous choices restored.')
            return
        self.get_application().set_tray_enabled(tray)
        self.get_application().place_window()
        self.update_controls()

    def apply_look(self):
        glass = self.preference_items.get('glass', True)
        self.get_application().use_glass_styles(glass)
        self.title_stack.set_visible_child_name('glass' if glass else 'synthwave')
        if glass:
            self.add_css_class('glass')
        else:
            self.remove_css_class('glass')
        if getattr(self, 'sky_switch', None) is not None:
            self.sky_switch.set_sensitive(not glass)
        self.backdrop.queue_draw()

    def glass_setting_changed(self, *_):
        glass = self.glass_switch.get_active()
        try:
            if not DEMO and self.preferences:
                self.preferences.set(self.notifications.get_active(), self.sound.get_active(), glass=glass)
                self.preference_items = self.preferences.items
            else:
                self.preference_items = {**self.preference_items, 'glass': glass}
        except OSError:
            self.status.set_text('The glass setting could not be saved.')
        self.apply_look()

    def sky_setting_changed(self, *_):
        animated = self.sky_switch.get_active()
        try:
            if not DEMO and self.preferences:
                self.preferences.set(self.notifications.get_active(), self.sound.get_active(), animated=animated)
                self.preference_items = self.preferences.items
            else:
                self.preference_items = {**self.preference_items, 'animated_sky': animated}
        except OSError:
            self.status.set_text('The sky setting could not be saved.')
        self.backdrop.queue_draw()

    def hide_to_bar(self):
        app = self.get_application()
        if hide_on_close(self.preference_items['tray_enabled'], app.tray_ready):
            self.settings_popover.popdown()
            self.set_visible(False)
            app.refresh_tray()
            return True
        self.status.set_text('No status-bar icon is available. Keep this window open or use Quit.')
        return False

    def close_requested(self, _):
        if self.quitting:
            return True
        if self.hide_to_bar():
            return True
        self.request_quit()
        return True

    def request_quit(self):
        if self.quitting:
            return False
        if self.gate.state == 'pending':
            self.get_application().show_chat()
            self.status.set_text('A text is being submitted. Wait for its result before quitting.')
            return False
        self.quitting = True
        self.get_application().begin_stop()
        self.settings_popover.popdown()
        self.set_sensitive(False)
        self.status.set_text('Closing the Bluetooth connection…')
        if self.worker:
            self.worker.command('stop')
        else:
            self.get_application().finish_quit()
        return False

    def populate_demo(self):
        self.phones = [{'name': 'Demo iPhone', 'address': 'demo'}]
        self.phone_choice.set_model(Gtk.StringList.new(['Demo iPhone']))
        self.connected = True
        self.status.set_text('Demo preview · fictional messages · Bluetooth and sending disabled.')
        self.messages = [Message('demo1', '+15550100101', 'Morgan', 'Hey! Are we still meeting at the coffee shop?', '20261020T190000'),
            Message('demo2', '+15550100101', 'Morgan', 'Absolutely. Sending this from my Linux laptop.', '20261020T190100', True, 'accepted'),
            Message('demo3', '+15550100101', 'Morgan', 'Nice. See you in ten minutes!', '20261020T190200'),
            Message('demo4', '+15550100101', 'Morgan', 'Ha, watch this before you go: https://www.youtube.com/watch?v=jNQXAC9IVRw', '20261020T190300', False, '', 'full')]
        self.select_peer('+15550100101', 'Morgan')


class Application(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='io.phonebridge.Preview' if DEMO else 'io.phonebridge.Desktop', flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.window = None
        self.tray = None
        self.tray_ready = False
        self.tray_held = False
        self.stopping_held = False
        self.placement_generation = 0

    def do_activate(self):
        if not self.window:
            register_fonts()
            self.synthwave_css = Gtk.CssProvider()
            self.synthwave_css.load_from_path(str(ROOT/'assets/style.css'))
            self.glass_css = Gtk.CssProvider()
            self.active_css = None
            self.theme_watcher = theme.Watcher(self.theme_changed)
            self.window = Window(self)
            self.set_tray_enabled(self.window.preference_items['tray_enabled'])
        self.show_chat()

    def use_glass_styles(self, glass):
        """Glass follows the running Omarchy theme; the synthwave look keeps its own colors."""
        display = Gdk.Display.get_default()
        if glass:
            self.glass_css.load_from_string(theme.stylesheet(ROOT/'assets/glass.css'))
        wanted = self.glass_css if glass else self.synthwave_css
        if self.active_css is not wanted:
            if self.active_css is not None:
                Gtk.StyleContext.remove_provider_for_display(display, self.active_css)
            Gtk.StyleContext.add_provider_for_display(display, wanted, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            self.active_css = wanted

    def theme_changed(self):
        if self.window and self.window.preference_items.get('glass', True):
            self.use_glass_styles(True)

    def set_tray_enabled(self, enabled):
        if DEMO:
            return
        if enabled and self.tray is None:
            try:
                from tray import StatusItem
                self.tray = StatusItem(self.toggle_chat, self.open_settings, self.window.request_quit,
                    lambda: self.window.get_visible(), self.tray_state)
                self.refresh_tray()
            except (dbus.DBusException, GLib.Error, OSError, ValueError, ImportError):
                # A missing watcher or unsupported tray must never strand a
                # hidden application. Keep the normal window usable.
                self.tray = None
                self.tray_state(False)
        elif not enabled and self.tray is not None:
            self.window.present()
            self.tray.close()
            self.tray = None
            self.tray_state(False)

    def tray_state(self, ready):
        self.tray_ready = ready
        if ready and not self.tray_held:
            self.hold()
            self.tray_held = True
        elif not ready:
            if self.window and not self.window.get_visible() and not self.window.quitting:
                self.show_chat()
            if self.tray_held:
                self.release()
                self.tray_held = False
            if self.window and not self.window.quitting:
                self.window.status.set_text('Status-bar icon is unavailable. The normal window remains usable.')
        if self.window:
            self.window.update_controls()

    def refresh_tray(self):
        if self.tray and self.window:
            self.tray.update(self.window.connected, self.window.unread.total)

    def place_window(self):
        if DEMO or not self.window or not self.window.get_visible():
            return False
        self.placement_generation += 1
        generation = self.placement_generation
        compact = self.window.preference_items['compact_window']
        def ready():
            if generation == self.placement_generation and self.window.get_visible():
                from presentation import place_window
                threading.Thread(target=place_window, args=(os.getpid(), compact), daemon=True).start()
            return False
        GLib.timeout_add(180, ready)
        return False

    def show_chat(self):
        if self.window:
            self.window.present()
            self.window.show_latest()
            self.place_window()
            self.window.mark_viewed()
            self.refresh_tray()
        return False

    def toggle_chat(self):
        if self.window.get_visible() and self.window.is_active():
            self.window.hide_to_bar()
        else:
            self.show_chat()
        return False

    def open_settings(self):
        self.show_chat()
        if self.window:
            self.window.settings_popover.popup()
        return False

    def begin_stop(self):
        if not self.stopping_held:
            self.hold()
            self.stopping_held = True

    def finish_quit(self):
        if self.tray:
            self.tray.close()
            self.tray = None
        if self.tray_held:
            self.release()
            self.tray_held = False
        if self.window:
            self.window.destroy()
            self.window = None
        if self.stopping_held:
            self.release()
            self.stopping_held = False
        self.quit()
        return False

if __name__ == '__main__':
    if '--setup' in sys.argv:
        from connect_phone import main as setup_main
        raise SystemExit(setup_main())
    DBusGMainLoop(set_as_default=True)
    raise SystemExit(Application().run([sys.argv[0]]))
