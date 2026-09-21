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
if __name__=='__main__':unittest.main()
