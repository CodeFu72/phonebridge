#!/usr/bin/env python3
"""Install PhoneBridge for the current Linux user. No root or background service."""
from datetime import datetime
import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import sys

ROOT = Path(__file__).resolve().parent.parent

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--omarchy-group', help='Existing Omarchy menu group to add PhoneBridge to')
    args = parser.parse_args()
    try:
        import dbus  # noqa: F401
        import cairo  # noqa: F401  (the synthwave look draws with it; missing it crashed first launch)
        import gi
    except ImportError as error:
        raise SystemExit(f'Missing a required package ({error.name}). On Omarchy run: '
                         'omarchy pkg add bluez bluez-utils bluez-obex python-dbus python-gobject python-cairo gtk4')
    gi.require_version('Gtk', '4.0')
    home = Path.home()
    data = Path(os.environ.get('XDG_DATA_HOME', str(home/'.local/share')))
    config = Path(os.environ.get('XDG_CONFIG_HOME', str(home/'.config')))
    install = data/'phonebridge/app'
    install.mkdir(parents=True, exist_ok=True)
    for name in ['app.py','bridge.py','model.py','phonebridge.py','send_test.py','receive_test.py','request_access.py','connect_phone.py','alerts.py','history.py','tray.py','presentation.py', 'attachment_test.py', 'composer.py', 'synthwave.py', 'linkpreview.py', 'theme.py']:
        shutil.copy2(ROOT/name, install/name)
    for document in ('HOW-TO.md', 'README.md', 'LICENSE'):
        shutil.copy2(ROOT/document, install/document)
    shutil.copytree(ROOT/'docs', install/'docs', dirs_exist_ok=True)
    shutil.copytree(ROOT/'assets', install/'assets', dirs_exist_ok=True)
    (install/'scripts').mkdir(exist_ok=True)
    shutil.copy2(ROOT/'scripts/check-phone.sh', install/'scripts/check-phone.sh')
    executable = home/'.local/bin/phonebridge'
    executable.parent.mkdir(parents=True, exist_ok=True)
    executable.write_text('#!/bin/sh\nexec '+shlex.quote(sys.executable)+' '+shlex.quote(str(install/'app.py'))+' "$@"\n')
    executable.chmod(0o755)
    setup_executable = home/'.local/bin/phonebridge-setup'
    setup_executable.write_text('#!/bin/sh\nexec '+shlex.quote(sys.executable)+' '+shlex.quote(str(install/'connect_phone.py'))+' "$@"\n')
    setup_executable.chmod(0o755)
    applications = data/'applications'; applications.mkdir(parents=True, exist_ok=True)
    icon_dir = data/'icons/hicolor/scalable/apps'; icon_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT/'assets/phonebridge.svg', icon_dir/'phonebridge.svg')
    def quote(value):
        return '"'+str(value).replace('\\','\\\\').replace('"','\\"').replace('%','%%')+'"'
    desktop = applications/'io.phonebridge.Desktop.desktop'
    desktop.write_text('[Desktop Entry]\nVersion=1.0\nType=Application\nName=PhoneBridge\nComment=Text through your nearby iPhone over Bluetooth\nExec='+quote(executable)+'\nIcon=phonebridge\nTerminal=false\nCategories=Network;Chat;\nStartupNotify=true\nStartupWMClass=io.phonebridge.Desktop\n')
    menu = config/'omarchy/extensions/omarchy-menu.jsonc'
    if menu.exists():
        try:
            entries = json.loads(menu.read_text())
        except json.JSONDecodeError:
            print('Omarchy menu uses comments; left it unchanged. PhoneBridge is installed in the application launcher.')
        else:
            backup = menu.with_name(menu.name+'.before-phonebridge-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
            shutil.copy2(menu, backup)
            group = args.omarchy_group or ('kirk' if 'kirk' in entries else 'apps')
            if group != 'apps' and group not in entries:
                raise ValueError('Requested Omarchy menu group does not exist: '+group)
            entries[group+'.phonebridge'] = {'label': 'PhoneBridge', 'icon': '󰏆', 'description': 'Text through your nearby iPhone', 'action': 'gtk-launch io.phonebridge.Desktop'}
            menu.write_text(json.dumps(entries, indent=2)+'\n')
    print('Installed PhoneBridge. Open it in the application launcher, or run '+str(executable))
    print('Connection guide: '+str(setup_executable))
    print('No Bluetooth settings, startup services or message data were changed.')

if __name__ == '__main__':
    main()
