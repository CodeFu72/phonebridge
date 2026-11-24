"""GTK-independent StatusNotifierItem and DBusMenu for the desktop bar."""
import os
import dbus
import dbus.service
from gi.repository import GLib

SNI = 'org.kde.StatusNotifierItem'
WATCHER = 'org.kde.StatusNotifierWatcher'
MENU = 'com.canonical.dbusmenu'
PROPS = 'org.freedesktop.DBus.Properties'


def icon_svg(connected, unread):
    count = max(0, min(int(unread), 100))
    color = '#9fe3d3' if connected else '#9caebc'
    badge = ''
    if count:
        number = str(count) if count < 100 else '99+'
        badge = f'<circle cx="24" cy="9" r="8" fill="#e66c63"/><text x="24" y="12" text-anchor="middle" font-family="sans-serif" font-size="8" font-weight="bold" fill="white">{number}</text>'
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"><path d="M4 7h23v17H12l-7 5v-5H4z" fill="{color}"/><path d="M9 12h13M9 17h9" stroke="#132a33" stroke-width="2" stroke-linecap="round"/>{badge}</svg>'


DIGITS = {
    '0': ('111','101','101','101','111'), '1': ('010','110','010','010','111'),
    '2': ('111','001','111','100','111'), '3': ('111','001','111','001','111'),
    '4': ('101','101','111','001','001'), '5': ('111','100','111','001','111'),
    '6': ('111','100','111','101','111'), '7': ('111','001','001','001','001'),
    '8': ('111','101','111','101','111'), '9': ('111','101','111','001','111'),
    '+': ('000','010','111','010','000')}


def icon_pixmaps(connected, unread):
    # Draw the small original speech-bubble icon directly. This avoids an SVG
    # loader helper/process dependency for a background status indicator.
    count = max(0, min(int(unread), 100))
    number = str(count) if count < 100 else '99+'
    text_x = 24-(len(number)*4-1)/2
    base = (159,227,211) if connected else (156,174,188)
    pixmaps = []
    for size in (22, 32, 48):
        pixels = bytearray()
        for iy in range(size):
            for ix in range(size):
                x, y = (ix+.5)*32/size, (iy+.5)*32/size
                color = (0, 0, 0, 0)
                if (4 <= x <= 27 and 6 <= y <= 24) or (x >= 5 and y >= 23 and x+y <= 35):
                    color = (255, *base)
                if (9 <= x <= 22 and 11 <= y <= 13) or (9 <= x <= 18 and 16 <= y <= 18):
                    color = (255,19,42,51)
                if count and (x-24)**2+(y-9)**2 <= 64:
                    color = (255,230,108,99)
                    tx, ty = int(x-text_x), int(y-6.5)
                    if x >= text_x and y >= 6.5 and 0 <= ty < 5 and 0 <= tx < len(number)*4-1:
                        char, column = tx//4, tx%4
                        if column < 3 and DIGITS[number[char]][ty][column] == '1':
                            color = (255,255,255,255)
                pixels.extend(color)
        pixmaps.append(dbus.Struct((dbus.Int32(size), dbus.Int32(size), dbus.ByteArray(pixels)), signature='iiay'))
    return dbus.Array(pixmaps, signature='(iiay)')


class Menu(dbus.service.Object):
    def __init__(self, bus, callbacks, is_visible):
        super().__init__(bus, '/MenuBar')
        self.callbacks, self.is_visible = callbacks, is_visible
        self.revision = 1

    def properties(self, item):
        if item == 0:
            return {'children-display': dbus.String('submenu')}
        if item == 3:
            return {'type': dbus.String('separator')}
        titles = {1: 'Hide chat' if self.is_visible() else 'Open chat', 2: 'Settings', 4: 'Quit PhoneBridge'}
        return {'label': dbus.String(titles.get(item, '')), 'enabled': dbus.Boolean(True), 'visible': dbus.Boolean(True)}

    @dbus.service.method(PROPS, in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface):
        return {'Version': dbus.UInt32(3), 'TextDirection': 'ltr', 'Status': 'normal', 'IconThemePath': dbus.Array([], signature='s')} if interface == MENU else {}

    @dbus.service.method(PROPS, in_signature='ss', out_signature='v')
    def Get(self, interface, property):
        return self.GetAll(interface)[property]

    @dbus.service.method(MENU, in_signature='iias', out_signature='u(ia{sv}av)')
    def GetLayout(self, parent, depth, names):
        def node(item):
            props = self.properties(item)
            if names:
                props = {key: value for key, value in props.items() if key in names}
            children = []
            if item == 0 and depth != 0:
                children = [dbus.Struct((dbus.Int32(i), dbus.Dictionary(self.properties(i), signature='sv'), dbus.Array([], signature='v')), signature='ia{sv}av', variant_level=1) for i in (1, 2, 3, 4)]
            return dbus.Struct((dbus.Int32(item), dbus.Dictionary(props, signature='sv'), dbus.Array(children, signature='v')), signature='ia{sv}av')
        return dbus.UInt32(self.revision), node(int(parent))

    @dbus.service.method(MENU, in_signature='aias', out_signature='a(ia{sv})')
    def GetGroupProperties(self, ids, names):
        return [(i, {k: v for k, v in self.properties(int(i)).items() if not names or k in names}) for i in ids]

    @dbus.service.method(MENU, in_signature='is', out_signature='v')
    def GetProperty(self, item, name):
        return self.properties(int(item))[name]

    @dbus.service.method(MENU, in_signature='isvu', out_signature='')
    def Event(self, item, event, data, timestamp):
        if event == 'clicked' and int(item) in self.callbacks:
            GLib.idle_add(self.callbacks[int(item)])

    @dbus.service.method(MENU, in_signature='a(isvu)', out_signature='ai')
    def EventGroup(self, events):
        for event in events:
            self.Event(*event)
        return []

    @dbus.service.method(MENU, in_signature='i', out_signature='b')
    def AboutToShow(self, item):
        return False

    @dbus.service.method(MENU, in_signature='ai', out_signature='aiai')
    def AboutToShowGroup(self, items):
        return [], []

    @dbus.service.signal(MENU, signature='ui')
    def LayoutUpdated(self, revision, parent):
        pass

    def refresh(self):
        self.revision += 1
        self.LayoutUpdated(self.revision, 0)


class StatusItem(dbus.service.Object):
    def __init__(self, toggle, settings, quit, visible, ready):
        self.bus = dbus.SessionBus()
        self.name = dbus.service.BusName(f'org.kde.StatusNotifierItem-{os.getpid()}-1', self.bus)
        super().__init__(self.name, '/StatusNotifierItem')
        self.toggle, self.on_settings, self.on_ready = toggle, settings, ready
        self.connected = False
        self.unread = 0
        self.available = False
        self.closed = False
        self.pixmaps = icon_pixmaps(False, 0)
        self.menu = Menu(self.bus, {1: toggle, 2: settings, 4: quit}, visible)
        self.watch = self.bus.add_signal_receiver(self.owner_changed, signal_name='NameOwnerChanged',
            dbus_interface='org.freedesktop.DBus', arg0=WATCHER)
        self.host_watches = [self.bus.add_signal_receiver(self.check_host, signal_name=signal,
            dbus_interface=WATCHER, bus_name=WATCHER) for signal in ('StatusNotifierHostRegistered', 'StatusNotifierHostUnregistered')]
        self.register()

    def register(self):
        if self.closed:
            return
        try:
            watcher = dbus.Interface(self.bus.get_object(WATCHER, '/StatusNotifierWatcher', introspect=False), WATCHER)
            watcher.RegisterStatusNotifierItem(self.name.get_name(), reply_handler=self.registered,
                error_handler=lambda error: self.registration_failed(), timeout=5)
        except dbus.DBusException:
            self.registration_failed()

    def registered(self):
        self.check_host()

    def check_host(self, *_):
        if self.closed:
            return
        try:
            properties = dbus.Interface(self.bus.get_object(WATCHER, '/StatusNotifierWatcher', introspect=False), PROPS)
            properties.Get(WATCHER, 'IsStatusNotifierHostRegistered', reply_handler=self.host_status,
                error_handler=lambda error: self.registration_failed(), timeout=3)
        except dbus.DBusException:
            self.registration_failed()

    def host_status(self, available):
        if not self.closed:
            self.available = bool(available)
            self.on_ready(self.available)

    def registration_failed(self):
        if not self.closed:
            self.available = False
            self.on_ready(False)

    def owner_changed(self, name, old, new):
        self.available = False
        self.on_ready(False)
        if new:
            self.register()

    def properties(self):
        status = 'Connected' if self.connected else 'Disconnected'
        tooltip = status + (f' · {self.unread} unread' if self.unread else ' · no unread texts')
        empty = dbus.Array([], signature='(iiay)')
        return {'Category': 'Communications', 'Id': 'phonebridge', 'Title': 'PhoneBridge',
            'Status': 'NeedsAttention' if self.unread else 'Active', 'WindowId': dbus.UInt32(0),
            'IconName': '', 'IconPixmap': self.pixmaps, 'AttentionIconName': '', 'AttentionIconPixmap': self.pixmaps,
            'OverlayIconName': '', 'OverlayIconPixmap': empty, 'AttentionMovieName': '',
            'ToolTip': dbus.Struct(('', empty, 'PhoneBridge', tooltip), signature='sa(iiay)ss'),
            'ItemIsMenu': dbus.Boolean(False), 'Menu': dbus.ObjectPath('/MenuBar')}

    @dbus.service.method(PROPS, in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface):
        return self.properties() if interface == SNI else {}

    @dbus.service.method(PROPS, in_signature='ss', out_signature='v')
    def Get(self, interface, property):
        return self.GetAll(interface)[property]

    @dbus.service.method(SNI, in_signature='ii', out_signature='')
    def Activate(self, x, y):
        GLib.idle_add(self.toggle)

    @dbus.service.method(SNI, in_signature='ii', out_signature='')
    def SecondaryActivate(self, x, y):
        GLib.idle_add(self.toggle)

    @dbus.service.method(SNI, in_signature='ii', out_signature='')
    def ContextMenu(self, x, y):
        # The host renders the exported DBusMenu; this method is a fallback.
        GLib.idle_add(self.on_settings)

    @dbus.service.method(SNI, in_signature='is', out_signature='')
    def Scroll(self, delta, orientation):
        pass

    @dbus.service.signal(SNI, signature='')
    def NewIcon(self):
        pass

    @dbus.service.signal(SNI, signature='')
    def NewAttentionIcon(self):
        pass

    @dbus.service.signal(SNI, signature='s')
    def NewStatus(self, status):
        pass

    @dbus.service.signal(SNI, signature='')
    def NewToolTip(self):
        pass

    def update(self, connected, unread):
        if (bool(connected), int(unread)) != (self.connected, self.unread):
            self.connected, self.unread = bool(connected), max(0, int(unread))
            self.pixmaps = icon_pixmaps(self.connected, self.unread)
            self.NewIcon(); self.NewAttentionIcon(); self.NewStatus('NeedsAttention' if self.unread else 'Active'); self.NewToolTip()
        self.menu.refresh()

    def close(self):
        self.closed = True
        self.watch.remove()
        for watch in self.host_watches:
            watch.remove()
        self.menu.remove_from_connection()
        self.remove_from_connection()
        self.name = None
