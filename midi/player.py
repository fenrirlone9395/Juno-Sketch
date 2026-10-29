"""Absolute monotonic deadlines; worker never accesses Tk widgets."""
import threading
import time
from copy import deepcopy
from queue import SimpleQueue
import mido
from models.project import PPQ

class Timeline:
    def __init__(self, project):
        self.changes = [(0,mido.bpm2tempo(project.bpm))]+sorted((t,v) for t,v in project.tempos if t>0)
    def seconds(self, tick):
        total, previous, tempo = 0.0, 0, self.changes[0][1]
        for t,v in self.changes[1:]:
            if t>tick: break
            total += (t-previous)*tempo/1e6/PPQ
            previous,tempo=t,v
        return total+(tick-previous)*tempo/1e6/PPQ
    def tick(self, seconds):
        previous,tempo=0,self.changes[0][1]
        for t,v in self.changes[1:]:
            duration=(t-previous)*tempo/1e6/PPQ
            if seconds<duration: break
            seconds-=duration
            previous,tempo=t,v
        return previous+seconds*1e6*PPQ/tempo

class Player:
    def __init__(self):
        self.cancel=threading.Event()
        self.thread=None
        self.errors=SimpleQueue()
        self.playing=False
        self.position=0
    def start(self, project, output, start=0):
        self.stop()
        project=deepcopy(project)
        self.timeline=Timeline(project)
        self.origin=time.perf_counter()-self.timeline.seconds(start)
        self.position=start
        self.cancel.clear()
        self.playing=True
        self.thread=threading.Thread(target=self._run,args=(project,output,start),daemon=True)
        self.thread.start()
    def _run(self,p,out,start):
        try:
            events=[]
            for tr in p.tracks:
                out.setup(tr)
                for tick,data in sorted(tr.events,key=lambda e:e[0]):
                    m=mido.Message.from_dict(data)
                    if tick<start: out.send(m)
                    else: events.append((tick,1,m))
                for n in tr.notes:
                    end=n.start+n.duration
                    if end<=start: continue
                    events.append((max(start,n.start),2,mido.Message('note_on',channel=tr.channel,note=n.pitch,velocity=n.velocity)))
                    events.append((end,0,mido.Message('note_off',channel=tr.channel,note=n.pitch)))
            for tick,_,message in sorted(events,key=lambda e:(e[0],e[1])):
                delay=self.origin+self.timeline.seconds(tick)-time.perf_counter()
                if self.cancel.wait(max(0,delay)): break
                out.send(message)
                self.position=tick
        except Exception as exc:
            self.errors.put(str(exc))
        finally:
            try: out.panic()
            except Exception as exc: self.errors.put(str(exc))
            self.playing=False
    def cursor(self):
        return self.timeline.tick(time.perf_counter()-self.origin) if self.playing else self.position
    def stop(self):
        self.cancel.set()
        if self.thread:
            self.thread.join(timeout=2)
            if self.thread.is_alive():
                raise RuntimeError('MIDI出力が応答していません')
        self.playing=False
