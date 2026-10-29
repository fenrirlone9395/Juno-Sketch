import mido
from midi.output import MidiOutput

class JunoDsOutput(MidiOutput):
    @staticmethod
    def ports():
        return mido.get_output_names()
    def __init__(self, port):
        super().__init__()
        if not port:
            raise ValueError('JUNO-DSのMIDIポートを選択してください')
        self.port = mido.open_output(port)
    def send(self, message):
        with self.lock:
            self.port.send(message)
    def close(self):
        try:
            super().close()
        finally:
            self.port.close()
