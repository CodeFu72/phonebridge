# Protocol references and acknowledgements

PhoneBridge is an independent implementation using BlueZ's public D-Bus interfaces. These references informed protocol choices; their implementation source has not been copied into this project.

- [BlueZ OBEX client](https://github.com/bluez/bluez/blob/master/doc/org.bluez.obex.Client.rst): MAP session setup and removal.
- [BlueZ message access](https://github.com/bluez/bluez/blob/master/doc/org.bluez.obex.MessageAccess.rst): inbox listing and PushMessage.
- [BlueZ message body API](https://github.com/bluez/bluez/blob/master/doc/org.bluez.obex.Message.rst): Message1.Get retrieves complete bMessages separately from listing previews.
- [BlueZ transfer API](https://github.com/bluez/bluez/blob/master/doc/org.bluez.obex.Transfer.rst): completion and failure status.
- [BlueZ advertisement API](https://github.com/bluez/bluez/blob/master/doc/org.bluez.LEAdvertisement.rst): bounded ANCS solicitation.
- [BlueZ MAP implementation](https://github.com/bluez/bluez/blob/master/obexd/client/map.c): `Charset` uses `utf8`, while the bMessage header uses `UTF-8`.
- [BlueFerry protocol findings](https://github.com/erikwb/blueferry/blob/main/PROTOCOL.md): experimental observations about iPhone permissions, message envelope structure and service ambiguity. These are empirical findings, not an Apple API guarantee.
- [iphonebridge](https://github.com/gabrielmeir53/iphonebridge): related experimental direct-Bluetooth bridge.

Apple, iPhone and iMessage are trademarks of Apple. PhoneBridge is unaffiliated. No Apple account credentials are requested by this application.

- [StatusNotifierItem specification](https://specifications.freedesktop.org/status-notifier-item/latest/status-notifier-item.html): tray properties, pixel data, activation and menu paths. The implementation uses the commonly deployed org.kde interface namespace supported by the local Omarchy tray.
- [Hyprland window documentation](https://wiki.hypr.land/Configuring/Basics/Window-Rules/): current configuration context. PhoneBridge uses runtime, process/window-targeted dispatches instead of adding a persistent rule. Non-Hyprland desktops retain normal placement.

Attachment probe API: [BlueZ Message1.Get(targetfile, attachment)](https://kernel.googlesource.com/pub/scm/bluetooth/bluez.git/+/52fb0d4de74bf3ed1fd43b1c8a14ab00f92824eb/doc/org.bluez.obex.Message.rst). The existing text reader passes false; the experimental photo probe passes true.
