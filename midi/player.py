"""Absolute monotonic deadlines; worker never accesses Tk widgets."""
import threading
import time
from copy import deepcopy
from queue import SimpleQueue
import mido
from models.project import PPQ
from services.track_state import audible_tracks


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
        self.cancel = threading.Event()
        self.thread = None
        self.errors = SimpleQueue()
        self.playing = False
        self.position = 0
        self._dispatch = threading.RLock()
        self._output = None
        self._tracks = []
        self._allowed = ()
        self._active = {}
        self._ready = False

    def start(self, project, output, start=0):
        self.stop()
        project = deepcopy(project)
        self.timeline = Timeline(project)
        self.origin = time.perf_counter()-self.timeline.seconds(start)
        self.position = start
        with self._dispatch:
            self._tracks = project.tracks
            self._output = output
            self._allowed = audible_tracks(project.tracks)
            self._active.clear()
            self._ready = False
        self.cancel.clear()
        self.playing = True
        self.thread = threading.Thread(target=self._run,args=(project,output,start),daemon=True)
        self.thread.start()

    def set_track_states(self, tracks):
        """Apply live mute/solo under the same lock used for MIDI dispatch."""
        allowed = audible_tracks(tracks)
        with self._dispatch:
            previous = self._allowed
            self._allowed = allowed
            if not self.playing or not self._ready:
                return
            try:
                for index, enabled in enumerate(allowed):
                    was_enabled = index < len(previous) and previous[index]
                    if was_enabled and not enabled:
                        for key in list(self._active):
                            if key[0] == index:
                                self._release_note(key)
                        # Also release notes held by a pedal after their Note Off.
                        self._output.send(mido.Message('control_change',channel=self._tracks[index].channel,
                                                       control=64,value=0))
                    elif enabled and not was_enabled:
                        self._output.setup(self._tracks[index])
                        # Restore controller/program state at the current cursor.
                        tick = self.cursor()
                        for event_tick, data in sorted(self._tracks[index].events,key=lambda e:e[0]):
                            if event_tick > tick:
                                break
                            self._output.send(mido.Message.from_dict(data))
            except Exception as exc:
                self.errors.put(str(exc))

    def begin_preview(self,index,pitch,velocity):
        """Preview without changing programs or releasing a sequenced unison."""
        with self._dispatch:
            if not self.playing or not self._ready or not self._allowed[index]:
                return None
            key=(index,'preview')
            if key in self._active:self._release_note(key)
            channel=self._tracks[index].channel
            if (channel,pitch) not in self._active.values():
                self._output.send(mido.Message('note_on',channel=channel,note=pitch,velocity=velocity))
            self._active[key]=(channel,pitch)
            return key

    def end_preview(self,key):
        with self._dispatch:
            if key in self._active:self._release_note(key)

    def _release_note(self, key):
        channel, pitch = self._active.pop(key)
        # Shared-channel unisons must not cut off another track's held note.
        if (channel,pitch) not in self._active.values():
            self._output.send(mido.Message('note_off',channel=channel,note=pitch))

    def _dispatch_event(self, index, kind, message, key=None):
        with self._dispatch:
            if kind == 'off':
                if key in self._active:
                    self._release_note(key)
            elif self._allowed[index]:
                self._output.send(message)
                if kind == 'on':
                    self._active[key] = (message.channel,message.note)

    def _run(self, project, output, start):
        try:
            events = []
            with self._dispatch:
                for index, track in enumerate(project.tracks):
                    if self._allowed[index]:
                        output.setup(track)
                    for tick,data in sorted(track.events,key=lambda e:e[0]):
                        message = mido.Message.from_dict(data)
                        if tick < start:
                            self._dispatch_event(index,'event',message)
                        else:
                            events.append((tick,1,index,'event',message,None))
                    for note in track.notes:
                        end = note.start+note.duration
                        if end <= start:
                            continue
                        key = (index,note.id)
                        events.append((max(start,note.start),2,index,'on',mido.Message('note_on',channel=track.channel,
                                                                                  note=note.pitch,velocity=note.velocity),key))
                        events.append((end,0,index,'off',mido.Message('note_off',channel=track.channel,note=note.pitch),key))
                self._ready = True
            for tick,_,index,kind,message,key in sorted(events,key=lambda e:(e[0],e[1])):
                delay = self.origin+self.timeline.seconds(tick)-time.perf_counter()
                if self.cancel.wait(max(0,delay)):
                    break
                self._dispatch_event(index,kind,message,key)
                self.position = tick
        except Exception as exc:
            self.errors.put(str(exc))
        finally:
            with self._dispatch:
                try:
                    output.panic()
                except Exception as exc:
                    self.errors.put(str(exc))
                self._active.clear()
                self._ready = False
                self.playing = False

    def cursor(self):
        return self.timeline.tick(time.perf_counter()-self.origin) if self.playing else self.position

    def stop(self):
        self.cancel.set()
        if self.thread:
            self.thread.join(timeout=2)
            if self.thread.is_alive():
                raise RuntimeError('MIDI出力が応答していません')
        self.playing = False
