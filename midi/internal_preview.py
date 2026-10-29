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
        self.graph, self.unit = ptr(), ptr()
        def check(status):
            if status:
                raise RuntimeError(f'AudioToolbox error: {status}')
        try:
            check(self.new(C.byref(self.graph)))
            nodes = []
            for typ, sub in [('aumu', 'dls '), ('auou', 'def ')]:
                node = C.c_int32()
                desc = Description(four(typ), four(sub), four('appl'), 0, 0)
                check(self.add(self.graph, C.byref(desc), C.byref(node)))
                nodes.append(node)
            check(self.open(self.graph))
            check(self.info(self.graph, nodes[0], None, C.byref(self.unit)))
            check(self.connect(self.graph, nodes[0], 0, nodes[1], 0))
            check(self.initialize(self.graph))
            check(self.start(self.graph))
        except Exception:
            if self.graph:
                self.dispose(self.graph)
            raise
    def send(self, message):
        # The system GM preview intentionally ignores JUNO bank numbers.
        if message.type == 'control_change' and message.control in (0, 32):
            return
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
