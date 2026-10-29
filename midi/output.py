from abc import ABC, abstractmethod
import threading
import mido

class MidiOutput(ABC):
    def __init__(self):
        self.lock = threading.RLock()
    @abstractmethod
    def send(self, message): ...
    def setup(self, track):
        for control, value in ((0, track.msb), (32, track.lsb)):
            self.send(mido.Message('control_change', channel=track.channel, control=control, value=value))
        self.send(mido.Message('program_change', channel=track.channel, program=track.program))
    def panic(self):
        for channel in range(16):
            for control in (64, 123, 120):
                self.send(mido.Message('control_change', channel=channel, control=control, value=0))
    def close(self):
        self.panic()
