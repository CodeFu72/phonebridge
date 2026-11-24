"""Place only this process's main window on the current Hyprland workspace."""
import json
import os
import re
import shutil
import subprocess


def placement_commands(clients, workspace, monitors, pid, compact):
    client = next((c for c in clients if c.get('pid') == pid and c.get('title') == 'PhoneBridge'
                   and c.get('class') == 'io.phonebridge.Desktop'), None)
    if not client or not re.fullmatch(r'0x[0-9a-fA-F]+', str(client.get('address', ''))):
        return []
    target = 'address:'+client['address']
    commands = []
    if compact:
        commands.append(['setfloating', target])
        wid = int(workspace['id'])
        commands.append(['movetoworkspacesilent', f'{wid},{target}'])
        monitor = next((m for m in monitors if m.get('activeWorkspace', {}).get('id') == wid), None)
        if monitor:
            scale = float(monitor.get('scale', 1)) or 1
            left, top, right, bottom = monitor.get('reserved', [0, 0, 0, 0])
            width = max(760, min(940, int(monitor['width']/scale)-left-right-40))
            height = max(500, min(640, int(monitor['height']/scale)-top-bottom-40))
            x = int(monitor.get('x', 0)+left+(monitor['width']/scale-left-right-width)/2)
            y = int(monitor.get('y', 0)+top+(monitor['height']/scale-top-bottom-height)/2)
            commands.extend([['resizewindowpixel', f'exact {width} {height},{target}'],
                             ['movewindowpixel', f'exact {x} {y},{target}']])
    else:
        commands.append(['settiled', target])
    commands.append(['focuswindow', target])
    return commands


_TARGET = re.compile(r'address:0x[0-9a-fA-F]+')


def lua_command(command):
    """Translate one legacy dispatch into Hyprland 0.56+ Lua syntax (hl.dsp...)."""
    name, argument = command
    def target(text):
        text = text.strip()
        if not _TARGET.fullmatch(text):
            raise ValueError('Unexpected window target.')
        return f"window = '{text}'"
    if name in ('setfloating', 'settiled'):
        action = 'enable' if name == 'setfloating' else 'disable'
        return f"hl.dsp.window.float({{ action = '{action}', {target(argument)} }})"
    if name == 'focuswindow':
        return f"hl.dsp.focus({{ {target(argument)} }})"
    if name == 'movetoworkspacesilent':
        workspace, window = argument.split(',', 1)
        return f"hl.dsp.window.move({{ workspace = '{int(workspace)}', follow = false, {target(window)} }})"
    if name in ('resizewindowpixel', 'movewindowpixel'):
        size, window = argument.split(',', 1)
        exact, x, y = size.split()
        if exact != 'exact':
            raise ValueError('Only exact placement is supported.')
        verb = 'resize' if name == 'resizewindowpixel' else 'move'
        return f"hl.dsp.window.{verb}({{ x = {int(x)}, y = {int(y)}, {target(window)} }})"
    raise ValueError(f'No Lua translation for {name}.')


def _dispatch(*args):
    result = subprocess.run(['hyprctl', 'dispatch', *args], capture_output=True, text=True, timeout=2)
    return result.returncode == 0 and 'error' not in (result.stdout + result.stderr).lower()


def place_window(pid, compact):
    if not os.environ.get('HYPRLAND_INSTANCE_SIGNATURE') or not shutil.which('hyprctl'):
        return
    try:
        def read(name):
            return json.loads(subprocess.run(['hyprctl', name, '-j'], capture_output=True, text=True, check=True, timeout=2).stdout)
        commands = placement_commands(read('clients'), read('activeworkspace'), read('monitors'), pid, compact)
        if not commands:
            return
        # Hyprland 0.56+ takes Lua (hl.dsp...); older versions take the classic syntax.
        if _dispatch(lua_command(commands[0])):
            for command in commands[1:]:
                _dispatch(lua_command(command))
        else:
            for command in commands:
                _dispatch(*command)
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        # Other compositors retain their normal window placement behavior.
        pass
