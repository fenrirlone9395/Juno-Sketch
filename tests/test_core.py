import json
import time
import mido
import pytest
from models.project import Project, Note, GRIDS, PPQ
from midi import smf
from midi.output import MidiOutput
from midi.player import Player, Timeline
from services import project_io
from services.undo import History

class Capture(MidiOutput):
    def __init__(self):
        super().__init__();self.messages=[]
    def send(self,m):self.messages.append(m)

def phrase():
    p=Project()
    p.tracks[0].msb=87;p.tracks[0].lsb=64;p.tracks[0].program=12
    p.tracks[0].notes=[Note(i*240,60+i%12,240 if i%2 else 160,70+i%40) for i in range(64)]
    p.tracks[9].notes=[Note(0,36,120,110)]
    p.tracks[1].events=[[960,mido.Message('control_change',channel=1,control=7,value=90).dict()]]
    p.tempos=[[0,500000],[7680,600000]]
    return p

def test_grid():
    assert GRIDS=={'1/4':960,'1/4T':640,'1/8':480,'1/8T':320,'1/16':240,'1/16T':160,'1/32':120,'1/32T':80}
    assert 3*GRIDS['1/32T']==GRIDS['1/16']

def test_project(tmp_path):
    p=phrase();p.ui.update(output='JUNO-DS',port='JUNO-DS',geometry='1200x800',xview=.2)
    path=tmp_path/'test.juno.json';project_io.save(p,path)
    assert project_io.load(path).data()==p.data()

def test_smf_roundtrip(tmp_path):
    p=phrase();path=tmp_path/'test.mid';smf.save(p,path)
    f=mido.MidiFile(path)
    assert f.type==1 and len(f.tracks)==17 and f.ticks_per_beat==960
    q,warnings=smf.load(path)
    # Empty musical tracks have setup events, retaining their slot.
    assert not warnings
    assert len(q.tracks)==16
    assert q.bpm==p.bpm
    assert q.tempos==p.tempos
    for a,b in zip(p.tracks,q.tracks):
        assert (a.channel,a.msb,a.lsb,a.program)==(b.channel,b.msb,b.lsb,b.program)
        assert sorted((n.start,n.pitch,n.duration,n.velocity) for n in a.notes)==sorted((n.start,n.pitch,n.duration,n.velocity) for n in b.notes)
        assert a.events==b.events

def test_type0_and_zero_velocity(tmp_path):
    f=mido.MidiFile(type=0,ticks_per_beat=480)
    f.tracks.append(mido.MidiTrack([mido.Message('note_on',note=60,velocity=90),mido.Message('note_on',note=60,velocity=0,time=240)]))
    path=tmp_path/'zero.mid';f.save(path)
    p,_=smf.load(path)
    assert p.tracks[0].notes[0].duration==480

def test_history():
    p=Project();h=History();h.push(p)
    p.tracks[0].notes.append(Note(0,60,160));q=h.undo(p)
    assert not q.tracks[0].notes
    assert h.redo(q).tracks[0].notes[0].duration==160

def test_tempo_mapping():
    p=phrase();t=Timeline(p)
    for tick in (0,960,7680,10000,16000):assert t.tick(t.seconds(tick))==pytest.approx(tick)

def test_setup_and_playback():
    p=Project(bpm=400);p.tracks[0].notes=[Note(0,60,40)]
    out=Capture();player=Player();player.start(p,out)
    player.thread.join(1)
    assert not player.playing and player.errors.empty()
    types=[m.type for m in out.messages]
    assert 'note_on' in types and 'note_off' in types
    assert [m.control for m in out.messages[:2]]==[0,32]
    assert out.messages[2].type=='program_change'

def test_stop_releases_notes():
    p=Project();p.tracks[0].notes=[Note(0,60,96000)]
    out=Capture();player=Player();player.start(p,out)
    time.sleep(.02);player.stop()
    assert not player.playing
    assert any(m.type=='control_change' and m.control==120 for m in out.messages)

def test_invalid_project_rejected(tmp_path):
    p=Project().data();p['tracks'][0]['notes']=[dict(start=-1,pitch=60,duration=1,velocity=90)]
    with pytest.raises(ValueError):Project.from_data(p)
