from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch
import dbus
from model import Message, Unread, Preferences, hide_on_close
from presentation import placement_commands
from tray import Menu, StatusItem, SNI, MENU, icon_pixmaps, icon_svg

class UnreadTests(unittest.TestCase):
    def test_initial_history_is_not_unread_and_counts_are_local_per_person(self):
        unread=Unread()
        a=Message('one','+15551234567','Example','private','')
        b=Message('two','+15557654321','Other','private','')
        unread.incoming([a,b],initial=True)
        self.assertEqual(unread.total,0)
        unread.incoming([a,b])
        unread.incoming([a])
        self.assertEqual(unread.total,2)
        unread.read('15551234567')
        self.assertEqual(unread.total,1)
        self.assertEqual(unread.count('+15557654321'),1)

    def test_foreground_person_at_latest_is_not_counted_as_unread(self):
        unread=Unread()
        unread.incoming([Message('one','+15551234567','Example','text','')],viewed_peer='15551234567')
        self.assertEqual(unread.total,0)

    def test_tray_preferences_migrate_and_survive_notification_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            file=Path(directory)/'preferences.json'
            file.write_text('{"notifications_enabled":true,"sound_enabled":false}')
            prefs=Preferences(file)
            self.assertTrue(prefs.items['tray_enabled'])
            prefs.set(True,False,tray=False,compact=False)
            prefs.set(False,True)
            saved=Preferences(file).items
            self.assertFalse(saved['tray_enabled']);self.assertFalse(saved['compact_window'])

    def test_hide_only_when_tray_is_both_enabled_and_registered(self):
        self.assertTrue(hide_on_close(True,True))
        for enabled,ready in [(False,True),(True,False),(False,False)]:
            self.assertFalse(hide_on_close(enabled,ready))

class TrayProtocolTests(unittest.TestCase):
    def test_icon_argb_dimensions_and_count_do_not_include_private_text(self):
        icons=icon_pixmaps(True,7)
        self.assertEqual([int(i[0]) for i in icons],[22,32,48])
        for width,height,pixels in icons:
            self.assertEqual(len(pixels),width*height*4)
        self.assertIn('99+',icon_svg(True,500))
        self.assertNotIn('private',icon_svg(True,2))

    def test_menu_layout_marshals_to_the_dbusmenu_wire_signature(self):
        fake=SimpleNamespace(revision=1,is_visible=lambda:True)
        fake.properties=lambda item:Menu.properties(fake,item)
        result=Menu.GetLayout(fake,0,-1,[])
        call=dbus.lowlevel.MethodCallMessage('org.example.Test','/MenuBar',MENU,'GetLayout')
        call.append(*result,signature='u(ia{sv}av)')
        self.assertEqual(len(result[1][2]),4)
        self.assertEqual(result[1][2][-1][1]['label'],'Quit PhoneBridge')

    def test_sni_properties_marshal_without_private_contact_metadata(self):
        fake=SimpleNamespace(connected=True,unread=3,pixmaps=icon_pixmaps(True,3))
        properties=StatusItem.properties(fake)
        call=dbus.lowlevel.MethodCallMessage('org.example.Test','/StatusNotifierItem','org.freedesktop.DBus.Properties','GetAll')
        call.append(properties,signature='a{sv}')
        self.assertEqual(properties['Status'],'NeedsAttention')
        self.assertEqual(properties['Menu'],'/MenuBar')
        self.assertIn('3 unread',properties['ToolTip'][3])

    def test_registered_watcher_without_a_host_is_not_safe_to_hide(self):
        fake=SimpleNamespace(closed=False,available=True,on_ready=Mock())
        StatusItem.host_status(fake,False)
        self.assertFalse(fake.available)
        fake.on_ready.assert_called_once_with(False)

    def test_registration_uses_the_bus_name_not_its_python_repr(self):
        fake=SimpleNamespace(closed=False,bus=Mock(),name=Mock(),registered=Mock(),registration_failed=Mock())
        fake.name.get_name.return_value='org.kde.StatusNotifierItem-123-1'
        watcher=Mock()
        with patch('tray.dbus.Interface',return_value=watcher):
            StatusItem.register(fake)
        self.assertEqual(watcher.RegisterStatusNotifierItem.call_args.args[0],'org.kde.StatusNotifierItem-123-1')

class PresentationTests(unittest.TestCase):
    def fixtures(self):
        clients=[{'pid':123,'class':'io.phonebridge.Desktop','title':'PhoneBridge','address':'0xabc'}]
        monitor=[{'width':1920,'height':1080,'scale':1.25,'x':0,'y':0,'reserved':[0,26,0,0],'activeWorkspace':{'id':4}}]
        return clients,{'id':4},monitor

    def test_compact_targets_only_own_main_window_and_current_workspace(self):
        clients,workspace,monitors=self.fixtures()
        commands=placement_commands(clients,workspace,monitors,123,True)
        self.assertEqual(commands[0],['setfloating','address:0xabc'])
        self.assertEqual(commands[1],['movetoworkspacesilent','4,address:0xabc'])
        self.assertTrue(all('address:0xabc' in command[1] for command in commands))
        self.assertEqual(placement_commands(clients,workspace,monitors,999,True),[])
        clients[0]['title']='Review your text'
        self.assertEqual(placement_commands(clients,workspace,monitors,123,True),[])

    def test_workspace_mode_tiles_without_moving_other_windows(self):
        clients,workspace,monitors=self.fixtures()
        commands=placement_commands(clients,workspace,monitors,123,False)
        self.assertEqual(commands,[['settiled','address:0xabc'],['focuswindow','address:0xabc']])

    def test_lua_translation_for_hyprland_056(self):
        from presentation import lua_command
        clients,workspace,monitors=self.fixtures()
        lua=[lua_command(c) for c in placement_commands(clients,workspace,monitors,123,True)]
        self.assertEqual(lua[0],"hl.dsp.window.float({ action = 'enable', window = 'address:0xabc' })")
        self.assertEqual(lua[1],"hl.dsp.window.move({ workspace = '4', follow = false, window = 'address:0xabc' })")
        self.assertTrue(lua[2].startswith('hl.dsp.window.resize({ x = '))
        self.assertTrue(lua[3].startswith('hl.dsp.window.move({ x = '))
        self.assertEqual(lua[-1],"hl.dsp.focus({ window = 'address:0xabc' })")
        self.assertEqual(lua_command(['settiled','address:0xabc']),"hl.dsp.window.float({ action = 'disable', window = 'address:0xabc' })")

    def test_lua_translation_rejects_unexpected_targets(self):
        from presentation import lua_command
        with self.assertRaises(ValueError):
            lua_command(['focuswindow',"address:0xabc' }) os.exit() --"])

class LifecycleTests(unittest.TestCase):
    def test_closing_to_tray_does_not_stop_worker(self):
        from app import Window
        window=SimpleNamespace(quitting=False,hide_to_bar=Mock(return_value=True),request_quit=Mock())
        self.assertTrue(Window.close_requested(window,None))
        window.request_quit.assert_not_called()

    def test_explicit_quit_waits_for_worker_shutdown(self):
        from app import Window
        from model import SendGate
        app=Mock()
        window=SimpleNamespace(quitting=False,gate=SendGate(),get_application=lambda:app,
            settings_popover=Mock(),set_sensitive=Mock(),status=Mock(),worker=Mock())
        Window.request_quit(window)
        self.assertTrue(window.quitting)
        app.begin_stop.assert_called_once()
        window.worker.command.assert_called_once_with('stop')
        app.finish_quit.assert_not_called()
        Window.event(window,'stopped',None)
        app.finish_quit.assert_called_once()

    def test_quit_is_blocked_while_a_send_is_pending(self):
        from app import Window
        from model import SendGate
        app=Mock();gate=SendGate();gate.begin()
        window=SimpleNamespace(quitting=False,gate=gate,get_application=lambda:app,status=Mock(),worker=Mock())
        Window.request_quit(window)
        window.worker.command.assert_not_called()
        app.begin_stop.assert_not_called()
        self.assertFalse(window.quitting)

    def test_worker_closes_connection_before_reporting_stopped(self):
        import queue
        from bridge import Bridge
        worker=Bridge.__new__(Bridge)
        worker.commands=queue.Queue();worker.commands.put(('stop',None))
        order=[]
        worker.close=lambda:order.append('close')
        worker.bus=Mock();worker.bus.close.side_effect=lambda:order.append('bus-close')
        worker.emit=lambda event,value:order.append(event)
        worker.run()
        self.assertEqual(order,['close','bus-close','stopped'])
