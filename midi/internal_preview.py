"""macOS system DLS synthesizer via AudioToolbox; no external SoundFont."""
import ctypes as C
import sys
from midi.output import MidiOutput

class Description(C.Structure):
    _fields_ = [(n, C.c_uint32) for n in ('type', 'subtype', 'manufacturer', 'flags', 'mask')]

def four(s):
    return int.from_bytes(s.encode('ascii'), 'big')

class InternalPreviewOutput(MidiOutput):
    def __init__(self):
        super().__init__()
        if sys.platform != 'darwin':
            raise RuntimeError('Internal PreviewはmacOS専用です')
        self.lib = C.CDLL('/System/Library/Frameworks/AudioToolbox.framework/AudioToolbox')
        def bind(name, args):
            f = getattr(self.lib, name)
            f.argtypes, f.restype = args, C.c_int32
            return f
        ptr, u32 = C.c_void_p, C.c_uint32
        self.new = bind('NewAUGraph', [C.POINTER(ptr)])
        self.add = bind('AUGraphAddNode', [ptr, C.POINTER(Description), C.POINTER(C.c_int32)])
        self.open = bind('AUGraphOpen', [ptr])
        self.info = bind('AUGraphNodeInfo', [ptr, C.c_int32, ptr, C.POINTER(ptr)])
        self.connect = bind('AUGraphConnectNodeInput', [ptr, C.c_int32, u32, C.c_int32, u32])
        self.initialize = bind('AUGraphInitialize', [ptr])
        self.start = bind('AUGraphStart', [ptr])
        self.stop = bind('AUGraphStop', [ptr])
        self.dispose = bind('DisposeAUGraph', [ptr])
        self.event = bind('MusicDeviceMIDIEvent', [ptr, u32, u32, u32, u32])
        self.set_parameter=bind('AudioUnitSetParameter',[ptr,u32,u32,u32,C.c_float,u32])
        self.graph, self.unit, self.mixer = ptr(), ptr(), ptr()
        def check(status):
            if status:
                raise RuntimeError(f'AudioToolbox error: {status}')
        try:
            check(self.new(C.byref(self.graph)))
            nodes = []
            for typ, sub in [('aumu', 'dls '), ('aumx', 'mcmx'), ('auou', 'def ')]:
                node = C.c_int32()
                desc = Description(four(typ), four(sub), four('appl'), 0, 0)
                check(self.add(self.graph, C.byref(desc), C.byref(node)))
                nodes.append(node)
            check(self.open(self.graph))
            check(self.info(self.graph, nodes[0], None, C.byref(self.unit)))
            check(self.info(self.graph,nodes[1],None,C.byref(self.mixer)))
            check(self.connect(self.graph, nodes[0], 0, nodes[1], 0))
            check(self.connect(self.graph, nodes[1], 0, nodes[2], 0))
            check(self.initialize(self.graph))
            check(self.start(self.graph))
        except Exception:
            if self.graph:
                self.dispose(self.graph)
            raise
    def set_master_volume(self,value):
        if not 0<=value<=1:raise ValueError('音量は0〜1です')
        with self.lock:
            # AUMultiChannelMixer output bus 0, Volume parameter (0).
            status=self.set_parameter(self.mixer,0,2,0,float(value),0)
            if status:raise RuntimeError(f'Master volume error: {status}')
    def send(self, message):
        if message.type=='sysex':return  # External-device messages never reach DLS.

        # Use the system DLS base GM banks. Never pass arbitrary JUNO banks
        # or unsupported variation banks through to the built-in sound bank.
        if message.type == 'control_change' and message.control == 0:
            value = message.value if message.value in (120, 121) else (120 if message.channel == 9 else 121)
            message = message.copy(value=value)
        elif message.type == 'control_change' and message.control == 32:
            message = message.copy(value=0)
        data = message.bytes()
        with self.lock:
            status = self.event(self.unit, data[0], data[1] if len(data)>1 else 0, data[2] if len(data)>2 else 0, 0)
            if status:
                raise RuntimeError(f'MIDI preview error: {status}')
    def close(self):
        try:
            super().close()
        finally:
            self.stop(self.graph)
            self.dispose(self.graph)
