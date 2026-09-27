"""Charybdis overlay: local, read-only, separate from the Studio connection."""
import ctypes
import json
import os
from pathlib import Path
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk
import serial
from serial.tools import list_ports

APP = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'CharybdisOverlay'
PALETTES = {
    'Midnight': ('#13232d', '#edf6fa', '#304653', '#215969', '#543e68', '#456236'),
    'Paper': ('#eef3f6', '#142c3b', '#dce5eb', '#b2dce8', '#dfc7ef', '#c4dfbd'),
    'Cyan': ('#08292e', '#e2fcff', '#19434a', '#246978', '#545079', '#316b5d'),
    'High contrast': ('#000000', '#ffffff', '#262626', '#003d73', '#59316d', '#24542d'),
}
ALIASES = {'Key Press':'key_press','Momentary Layer':'momentary_layer','Transparent':'trans',
'Mouse Key Press':'mouse_key_press','Bluetooth':'bluetooth','Output Selection':'outputs',
'Studio Unlock':'studio_unlock','None':'none','To Layer':'to_layer'}
HID = {i+4:chr(65+i) for i in range(26)}
HID.update({i+30:str((i+1)%10) for i in range(10)})
HID.update({40:'Enter',41:'Esc',42:'Backspace',43:'Tab',44:'Space',45:'-',46:'=',47:'[',48:']',49:'\\',50:'#',51:';',52:"'",53:'`',54:',',55:'.',56:'/',57:'Caps Lock',70:'Print Screen',71:'Scroll Lock',72:'Pause',73:'Insert',74:'Home',75:'Page Up',76:'Delete',77:'End',78:'Page Down',79:'Right',80:'Left',81:'Down',82:'Up',83:'Num Lock',84:'KP /',85:'KP *',86:'KP -',87:'KP +',88:'KP Enter',98:'KP 0',99:'KP .',103:'KP =',224:'L Ctrl',225:'L Shift',226:'L Alt',227:'L Super',228:'R Ctrl',229:'R Shift',230:'R Alt',231:'R Super'})
HID.update({58+i:'F'+str(i+1) for i in range(12)})
HID.update({89+i:'KP '+str(i+1) for i in range(9)})
MEDIA={182:'Previous track',181:'Next track',205:'Play / pause',234:'Volume -',233:'Volume +',226:'Mute'}
SHIFT=dict(zip('1234567890-=[]\\;\'`,./','!@#$%^&*()_+{}|:"~<>?'))
MODS=['Ctrl','Shift','Alt','Super','R Ctrl','R Shift','R Alt','R Super']

def canonical(name):
    return name.lower().replace('-', '_').split('/')[-1]

def key_label(value, mods=0, caps=False):
    code=value&65535;page=(value>>16)&255;implicit=(value>>24)&255
    text=(HID if page==7 else MEDIA if page==12 else {}).get(code, f'HID {page:02X}:{code:04X}')
    shift=bool((mods|implicit)&0x22)
    if page==7 and 4<=code<=29:
        text=text.upper() if shift != caps else text.lower()
    elif page==7 and shift:text=SHIFT.get(text,text)
    # Show explicit chord modifiers, but avoid duplicating Shift when rendered as a symbol.
    chord=[n for i,n in enumerate(MODS) if implicit&(1<<i) and (i not in (1,5) or len(text)!=1)]
    if chord:text='+'.join(chord+[text])
    return text

def resolve(layers, mask, default, position):
    """Return the first opaque binding in firmware layer priority order."""
    for layer in reversed(layers):
        if not (mask&(1<<layer['id']) or layer['id']==default):continue
        if position>=len(layer['bindings']):continue
        binding=layer['bindings'][position]
        # ZMK's missing behavior is not an explicit &none; allow lower layers.
        if not binding[0] or canonical(binding[0]) in ('trans','transparent'):continue
        return binding,layer['id']
    return ['none',0,0],default

def label(binding, names, mods=0, caps=False):
    raw,p,q=binding;name=canonical(raw)
    if name=='key_press':return key_label(p,mods,caps),'key'
    if name in ('momentary_layer','toggle_layer','to_layer','sticky_layer'):
        return {'momentary_layer':'Hold','toggle_layer':'Toggle','to_layer':'Go to','sticky_layer':'Sticky'}[name]+'\n'+names.get(p,f'Layer {p}'),'layer'
    if name=='mouse_key_press':return '+'.join(n for bit,n in [(1,'Left click'),(2,'Right click'),(4,'Middle click'),(8,'Mouse 4'),(16,'Mouse 5')] if p&bit) or 'Mouse', 'mouse'
    if name in ('layer_tap','mod_tap'):
        hold=names.get(p,f'Layer {p}') if name=='layer_tap' else key_label(p)
        return 'Tap '+key_label(q,mods,caps)+'\nHold '+hold,'layer'
    if name=='bluetooth':return ({0:'Clear pairing',1:'Next BT',2:'Previous BT',3:f'BT {q+1}',4:'Clear all BT',5:f'Disconnect BT {q+1}'}.get(p,f'BT {p}/{q}')),'special'
    if name=='outputs':return {0:'Toggle output',1:'USB output',2:'BLE output',3:'No output'}.get(p,'Output'),'special'
    if name=='studio_unlock':return 'Studio unlock','special'
    if name=='none':return '—','key'
    if name in ('key_toggle','sticky_key'):return ('Toggle ' if name=='key_toggle' else 'Sticky ')+key_label(p,mods,caps),'special'
    if name=='caps_word':return 'Caps Word','special'
    return f'{raw}\n{p} / {q}','special'

class Stream:
    def __init__(self):self.pending=None;self.layout=None
    def feed(self, item):
        kind=item.get('type')
        if kind=='begin':
            if item.get('protocol')!=1:raise ValueError('Unsupported overlay firmware protocol')
            self.pending={**item,'layers':[]}
        elif kind=='layer' and self.pending is not None:self.pending['layers'].append(item)
        elif kind=='end' and self.pending is not None:
            candidate=self.pending;self.pending=None
            if item.get('valid') and item.get('revision')==candidate['revision']:
                if not candidate['layers'] or not 1<=len(candidate['keys'])<=256:raise ValueError('Invalid keymap')
                if any(len(l['bindings'])!=len(candidate['keys']) for l in candidate['layers']):raise ValueError('Incomplete keymap')
                self.layout=candidate;return 'layout',candidate
        elif kind=='state':return 'state',item
        return None

class Reader(threading.Thread):
    def __init__(self, events, stop):super().__init__(daemon=True);self.events=events;self.stop=stop
    def run(self):
        while not self.stop.is_set():
            found=False
            ports=[p for p in list_ports.comports() if p.vid==0x1d50 and p.pid==0x615e]
            ports.sort(key=lambda p:'overlay' not in (p.description+' '+str(p.interface)).lower())
            for p in ports:
                if self.stop.is_set():return
                try:
                    with serial.Serial(p.device,115200,timeout=.25,write_timeout=.25) as ser:
                        ser.dtr=True;stream=Stream();deadline=time.monotonic()+2.5;last=time.monotonic();seen=False;buf=bytearray()
                        while not self.stop.is_set():
                            data=ser.read(max(1,min(ser.in_waiting,8192)))
                            buf.extend(data)
                            if len(buf)>262144:raise ValueError('Unexpected serial data')
                            while b'\n' in buf:
                                line,_,buf=buf.partition(b'\n')
                                try: item=json.loads(line)
                                except (ValueError,UnicodeDecodeError):continue
                                if not isinstance(item,dict):continue
                                if item.get('type') not in ('begin','layer','end','state'):continue
                                if not seen:self.events.put(('status','Connected: '+p.device));seen=True;found=True
                                last=time.monotonic();event=stream.feed(item)
                                if event:self.events.put(event)
                            now=time.monotonic()
                            if not seen and now>deadline:break
                            if seen and now-last>5:raise TimeoutError('Keyboard disconnected or suspended')
                except (serial.SerialException,OSError,ValueError,TimeoutError) as e:
                    if found:self.events.put(('offline',str(e)))
                if found:break
            if not found:self.events.put(('offline','Waiting for overlay firmware over USB…'))
            self.stop.wait(2)

class KeyboardActivity:
    """Keep only an activity flag. Never read or store the key-code payload."""
    def __init__(self):
        self.pressed=threading.Event();self.ready=threading.Event();self.error=None
        self.thread_id=None;self.thread=None
        if sys.platform=='win32':
            self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
            if not self.ready.wait(3):self.error='Keyboard activity listener did not start'
    def run(self):
        from ctypes import wintypes as w
        u=ctypes.WinDLL('user32',use_last_error=True);k=ctypes.WinDLL('kernel32',use_last_error=True)
        cbtype=ctypes.WINFUNCTYPE(ctypes.c_ssize_t,ctypes.c_int,w.WPARAM,w.LPARAM)
        u.SetWindowsHookExW.argtypes=[ctypes.c_int,cbtype,w.HINSTANCE,w.DWORD];u.SetWindowsHookExW.restype=w.HANDLE
        u.CallNextHookEx.argtypes=[w.HANDLE,ctypes.c_int,w.WPARAM,w.LPARAM];u.CallNextHookEx.restype=ctypes.c_ssize_t
        u.UnhookWindowsHookEx.argtypes=[w.HANDLE];u.UnhookWindowsHookEx.restype=w.BOOL
        u.GetMessageW.argtypes=[ctypes.POINTER(w.MSG),w.HWND,w.UINT,w.UINT];u.GetMessageW.restype=w.BOOL
        k.GetModuleHandleW.argtypes=[w.LPCWSTR];k.GetModuleHandleW.restype=w.HMODULE
        k.GetCurrentThreadId.restype=w.DWORD
        def callback(code,message,payload):
            if code==0 and message in (0x100,0x104):self.pressed.set()
            return u.CallNextHookEx(None,code,message,payload)
        self.callback=cbtype(callback)
        hook=u.SetWindowsHookExW(13,self.callback,k.GetModuleHandleW(None),0)
        if not hook:
            self.error='Keyboard activity unavailable (Windows error %s)' % ctypes.get_last_error()
            self.ready.set();return
        self.thread_id=k.GetCurrentThreadId()
        # Ensure this thread has a message queue before advertising readiness.
        message=w.MSG();u.PeekMessageW(ctypes.byref(message),None,0,0,0)
        self.ready.set()
        try:
            while u.GetMessageW(ctypes.byref(message),None,0,0)>0:
                u.TranslateMessage(ctypes.byref(message));u.DispatchMessageW(ctypes.byref(message))
        finally:u.UnhookWindowsHookEx(hook)
    def consume(self):
        if not self.pressed.is_set():return False
        self.pressed.clear();return True
    def close(self):
        if self.thread_id:
            ctypes.windll.user32.PostThreadMessageW(self.thread_id,0x12,0,0)
            if self.thread:self.thread.join(timeout=1)

class App:
    def __init__(self):
        APP.mkdir(parents=True,exist_ok=True)
        self.settings={'opacity':85,'width':1050,'duration':5,'palette':'Midnight','x':40,'y':650,'clickthrough':True,'transparent_background':False,'refresh_typing':True}
        try:self.settings.update(json.loads((APP/'settings.json').read_text()))
        except (OSError,ValueError):pass
        self.root=tk.Tk();self.root.title('Charybdis Overlay');self.root.geometry('540x610')
        self.events=queue.Queue();self.stop=threading.Event();self.map=None;self.state={'layers':1,'default':0,'mods':0};self.signature=None;self.hide_at=0;self.online=False;self.last_caps=False
        self.overlay=tk.Toplevel(self.root);self.overlay.withdraw();self.overlay.overrideredirect(True);self.overlay.attributes('-topmost',True)
        self.canvas=tk.Canvas(self.overlay,highlightthickness=0);self.canvas.pack(fill='both',expand=True)
        box=ttk.Frame(self.root,padding=18);box.pack(fill='both',expand=True)
        ttk.Label(box,text='Charybdis Overlay',font=('Segoe UI',20,'bold')).pack(anchor='w')
        ttk.Label(box,text='Live layers • Shift symbols • Automatic keymap refresh').pack(anchor='w',pady=(2,14))
        self.status=tk.StringVar(value='Starting…');ttk.Label(box,textvariable=self.status,wraplength=465).pack(anchor='w',pady=(0,10))
        self.vars={}
        for key,title,lo,hi in [('opacity','Opacity (%)',20,100),('width','Width (pixels)',650,1600),('duration','Hide delay (seconds; 0 = always visible)',0,30)]:
            row=ttk.Frame(box);row.pack(fill='x',pady=3);ttk.Label(row,text=title).pack(anchor='w');v=tk.DoubleVar(value=self.settings[key]);self.vars[key]=v
            ttk.Scale(row,from_=lo,to=hi,variable=v,command=lambda _,k=key:self.changed(k)).pack(side='left',fill='x',expand=True)
            ttk.Label(row,textvariable=v,width=7).pack(side='right')
        row=ttk.Frame(box);row.pack(fill='x',pady=7);ttk.Label(row,text='Palette').pack(side='left');self.vars['palette']=tk.StringVar(value=self.settings['palette']);combo=ttk.Combobox(row,textvariable=self.vars['palette'],values=list(PALETTES),state='readonly');combo.pack(side='right');combo.bind('<<ComboboxSelected>>',lambda _:self.changed('palette'))
        row=ttk.Frame(box);row.pack(fill='x',pady=5)
        for k in ('x','y'):
            ttk.Label(row,text=k.upper()+' position').pack(side='left');v=tk.IntVar(value=self.settings[k]);self.vars[k]=v
            sp=ttk.Spinbox(row,from_=-10000,to=10000,width=7,textvariable=v,command=lambda k=k:self.changed(k));sp.pack(side='left',padx=5);sp.bind('<Return>',lambda _,k=k:self.changed(k))
        self.vars['clickthrough']=tk.BooleanVar(value=self.settings['clickthrough']);ttk.Checkbutton(box,text='Click through overlay (Windows)',variable=self.vars['clickthrough'],command=lambda:self.changed('clickthrough')).pack(anchor='w',pady=5)
        for key,title in [('transparent_background','Transparent background (keep the keys visible)'),('refresh_typing','Keep visible while typing (all keyboards)')]:
            self.vars[key]=tk.BooleanVar(value=self.settings[key])
            ttk.Checkbutton(box,text=title,variable=self.vars[key],command=lambda k=key:self.changed(k)).pack(anchor='w',pady=4)
        row=ttk.Frame(box);row.pack(fill='x',pady=7);ttk.Button(row,text='Show overlay',command=self.show).pack(side='left');ttk.Button(row,text='Hide overlay',command=self.overlay.withdraw).pack(side='left',padx=8)
        self.preview=tk.StringVar();self.preview_box=ttk.Combobox(row,textvariable=self.preview,state='readonly',width=15);self.preview_box.pack(side='right');self.preview_box.bind('<<ComboboxSelected>>',self.preview_layer)
        ttk.Label(box,text='USB required. Studio can stay open.\nSymbol labels use US English; Caps Lock follows Windows.\nClosing this window quits the overlay.',foreground='#526675').pack(anchor='w',pady=6)
        self.activity=KeyboardActivity()
        if self.activity.error:ttk.Label(box,text=self.activity.error,foreground='#b04030').pack(anchor='w')
        self.root.protocol('WM_DELETE_WINDOW',self.quit)
        cache=APP/'keymap.json';baseline=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))/'baseline.json'
        try:self.map=json.loads((cache if cache.exists() else baseline).read_text());self.update_layers()
        except (OSError,ValueError):pass
        Reader(self.events,self.stop).start();self.root.after(40,self.tick)
    def changed(self,k):
        try:self.settings[k]=round(self.vars[k].get()) if k in ('opacity','width','duration') else self.vars[k].get()
        except tk.TclError:return
        (APP/'settings.json').write_text(json.dumps(self.settings));self.show()
    def caps(self):return bool(ctypes.windll.user32.GetKeyState(0x14)&1) if sys.platform=='win32' else False
    def update_layers(self):
        self.preview_box['values']=[f"{l['id']}: {l['name']}" for l in self.map['layers']]
    def preview_layer(self,event=None):
        try:lid=int(self.preview.get().split(':')[0]);self.state={'layers':1|(1<<lid),'default':0,'mods':0};self.signature=None;self.show()
        except ValueError:pass
    def noactivate(self):
        if sys.platform!='win32':return
        u=ctypes.windll.user32
        u.GetParent.argtypes=[ctypes.c_void_p];u.GetParent.restype=ctypes.c_void_p
        u.GetWindowLongW.argtypes=[ctypes.c_void_p,ctypes.c_int];u.GetWindowLongW.restype=ctypes.c_long
        u.SetWindowLongW.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_long]
        hwnd=u.GetParent(self.overlay.winfo_id());style=u.GetWindowLongW(hwnd,-20)|0x08000000|0x80|0x80000
        style=(style|0x20) if self.settings['clickthrough'] else (style&~0x20)
        u.SetWindowLongW(hwnd,-20,style)
    def show(self):
        if not self.map:return
        self.draw();self.overlay.update_idletasks();self.noactivate();self.overlay.deiconify();self.noactivate()
        self.hide_at=time.monotonic()+self.settings['duration'] if self.settings['duration'] else 0
    def typing_activity(self):
        if not self.settings['refresh_typing'] or not self.online or not self.map:return
        if self.overlay.state()=='withdrawn':self.show()
        else:self.hide_at=time.monotonic()+self.settings['duration'] if self.settings['duration'] else 0
    def draw(self):
        palette=PALETTES.get(self.settings['palette'],PALETTES['Midnight']);bg,fg,key,layer,special,mouse=palette
        width=max(650,min(1600,self.settings['width']));geo=self.map['keys'];extent=max(k[0]+k[2] for k in geo);height_units=max(k[1]+k[3] for k in geo);scale=(width-24)/extent;height=int(height_units*scale)+60
        x=int(self.settings['x']);y=int(self.settings['y'])
        # Keep the initial position visible on smaller screens.
        y=min(y,max(0,self.root.winfo_screenheight()-height))
        self.overlay.geometry(f'{width}x{height}{x:+d}{y:+d}');self.overlay.attributes('-alpha',max(.2,min(1,self.settings['opacity']/100)))
        backdrop='#ff00ff' if self.settings['transparent_background'] and sys.platform=='win32' else bg
        if sys.platform=='win32':self.overlay.attributes('-transparentcolor',backdrop if self.settings['transparent_background'] else '')
        self.canvas.configure(width=width,height=height,bg=backdrop);self.canvas.delete('all')
        ls=self.map['layers'];names={l['id']:l['name'] for l in ls};active=[l for l in ls if self.state['layers']&(1<<l['id']) or l['id']==self.state['default']]
        title=' + '.join(l['name'] for l in active) or 'Typing';mods=self.state['mods'];caps=self.caps()
        flags=[n for i,n in enumerate(MODS) if mods&(1<<i)];title+=('  |  '+' + '.join(flags)) if flags else '';title+='  |  CAPS' if caps else '';title+='  [preview / offline]' if not self.online else ''
        self.canvas.create_text(14,18,text=title,fill=fg,anchor='w',font=('Segoe UI',12,'bold'))
        for i,k in enumerate(geo):
            b,source=resolve(ls,self.state['layers'],self.state['default'],i);s,cat=label(b,names,mods,caps)
            xx=12+k[0]*scale;yy=39+k[1]*scale;ww=k[2]*scale-4;hh=k[3]*scale-4
            fill={'key':key,'layer':layer,'special':special,'mouse':mouse}[cat]
            self.canvas.create_rectangle(xx,yy,xx+ww,yy+hh,fill=fill,outline=bg)
            size=max(7,min(13,int(ww/max(6,max(map(len,s.split('\n'))))*1.35)))
            self.canvas.create_text(xx+ww/2,yy+hh/2,text=s,fill=fg,width=ww-5,font=('Segoe UI',size,'bold'))
    def tick(self):
        redraw=False
        while True:
            try:kind,payload=self.events.get_nowait()
            except queue.Empty:break
            if kind=='layout':
                self.map=payload;(APP/'keymap.json').write_text(json.dumps(payload));self.update_layers();redraw=True
            elif kind=='state':
                self.online=True;sig=(payload['layers'],payload['mods'],payload['default']);self.state=payload
                if sig!=self.signature:self.signature=sig;redraw=True
            elif kind=='status':self.status.set(payload)
            elif kind=='offline':self.status.set(payload);self.online=False;self.signature=None;self.overlay.withdraw()
        caps=self.caps()
        if caps!=self.last_caps:self.last_caps=caps;redraw=True
        if redraw:self.show()
        if self.activity.consume():self.typing_activity()
        if self.hide_at and time.monotonic()>self.hide_at:self.overlay.withdraw();self.hide_at=0
        self.root.after(40,self.tick)
    def quit(self):self.stop.set();self.activity.close();self.root.destroy()
    def run(self):self.root.mainloop()

if __name__=='__main__':App().run()
