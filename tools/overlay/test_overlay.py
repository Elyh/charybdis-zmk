import unittest
from overlay import resolve, label, key_label, Stream
class Tests(unittest.TestCase):
    def test_layers(self):
        layers=[{'id':0,'bindings':[['key_press',0x70004,0]]},{'id':6,'bindings':[['trans',0,0]]}]
        self.assertEqual(resolve(layers,65,0,0)[1],0)
        layers[1]['bindings'][0]=['none',0,0]
        self.assertEqual(resolve(layers,65,0,0)[1],6)
        layers.reverse() # priority follows exported order, not numeric ID
        self.assertEqual(resolve(layers,65,0,0)[1],0)
    def test_shift(self):
        self.assertEqual(key_label(0x7001e,2),'!')
        self.assertEqual(key_label(0x70004,32),'A')
        self.assertEqual(key_label(0x70004,2,True),'a')
        self.assertEqual(key_label(0x01070006),'Ctrl+c')
    def test_atomic_snapshot(self):
        s=Stream();s.feed({'type':'begin','protocol':1,'revision':5,'keys':[[0,0,100,100]]})
        s.feed({'type':'layer','id':0,'bindings':[['key_press',0x70004,0]]})
        self.assertIsNone(s.layout)
        self.assertIsNone(s.feed({'type':'end','revision':5,'valid':False}))
        s.feed({'type':'begin','protocol':1,'revision':6,'keys':[[0,0,100,100]]})
        s.feed({'type':'layer','id':0,'bindings':[['key_press',0x70005,0]]})
        self.assertEqual(s.feed({'type':'end','revision':6,'valid':True})[0],'layout')
        self.assertEqual(s.layout['layers'][0]['bindings'][0][1],0x70005)
    def test_hold_and_tap(self):
        self.assertEqual(label(['layer_tap',6,0x7002b],{6:'Number Pad'})[0],'Tap Tab\nHold Number Pad')

# Exercise real Windows widgets and native no-activation flags without hardware.
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
import overlay
@unittest.skipUnless(sys.platform == 'win32', 'Windows GUI integration')
class WindowsGui(unittest.TestCase):
    def test_window_and_layer_updates(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(overlay,'APP',Path(temp)), patch.object(overlay.Reader,'start'):
            app=overlay.App()
            try:
                app.root.update()
                self.assertIsNotNone(app.map)
                app.state={'layers':17,'default':0,'mods':2}
                app.show();app.root.update()
                self.assertGreater(len(app.canvas.find_all()),56)
                app.events.put(('state',{'layers':65,'default':0,'mods':0}))
                app.tick();app.root.update()
                self.assertEqual(app.state['layers'],65)
                self.assertIsNone(app.activity.error)
                app.settings['transparent_background']=True
                app.show();app.root.update()
                self.assertEqual(app.overlay.attributes('-transparentcolor').lower(),'#ff00ff')
                app.settings['transparent_background']=False
                app.show()
                self.assertEqual(app.overlay.attributes('-transparentcolor'),'')
                app.online=True;app.hide_at=1
                app.typing_activity()
                self.assertGreater(app.hide_at,overlay.time.monotonic())
                app.overlay.withdraw();app.typing_activity();app.root.update()
                self.assertNotEqual(app.overlay.state(),'withdrawn')
                app.settings['refresh_typing']=False;app.hide_at=123
                app.typing_activity();self.assertEqual(app.hide_at,123)
                app.settings['refresh_typing']=True;app.settings['duration']=0
                app.typing_activity();self.assertEqual(app.hide_at,0)
                app.activity.consume()
                # F24 exercises the native hook without typing into another app.
                overlay.ctypes.windll.user32.keybd_event(0x87,0,0,0)
                overlay.ctypes.windll.user32.keybd_event(0x87,0,2,0)
                self.assertTrue(app.activity.pressed.wait(2), 'Native key press was not detected')
            finally:app.quit()

if __name__=='__main__':unittest.main()
