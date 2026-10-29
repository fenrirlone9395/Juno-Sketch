import threading
import mido
from models.project import Project, Note
from midi.player import Player
from services.track_state import audible_tracks
from services import project_io
from midi import smf
from test_core import Capture


def test_solo_and_mute_priority():
    p=Project()
    assert all(audible_tracks(p.tracks))
    p.tracks[1].solo=True;p.tracks[2].solo=True;p.tracks[2].muted=True
    assert [i for i,v in enumerate(audible_tracks(p.tracks)) if v]==[1]
    p.tracks[1].muted=True
    assert not any(audible_tracks(p.tracks))


def test_scheduler_filters_solo_and_muted_tracks():
    p=Project(bpm=400)
    for i in range(3):p.tracks[i].notes=[Note(0,60+i,40)]
    p.tracks[0].solo=True;p.tracks[1].solo=True;p.tracks[1].muted=True
    out=Capture();player=Player();player.start(p,out);player.thread.join(1)
    assert not player.playing and player.errors.empty()
    assert [(m.channel,m.note) for m in out.messages if m.type=='note_on']==[(0,60)]


def test_live_mute_releases_notes_without_stopping_other_track():
    ready=threading.Event()
    class LiveCapture(Capture):
        def send(self,m):
            super().send(m)
            if sum(msg.type=='note_on' for msg in self.messages)==2:ready.set()
    p=Project();p.tracks[0].notes=[Note(0,60,9600)];p.tracks[1].notes=[Note(0,64,9600)]
    out=LiveCapture();player=Player();player.start(p,out)
    try:
        assert ready.wait(1)
        p.tracks[0].muted=True;player.set_track_states(p.tracks)
        assert player.playing
        assert any(m.type=='note_off' and m.channel==0 and m.note==60 for m in out.messages)
        assert not any(m.type=='note_off' and m.channel==1 for m in out.messages)
        assert any(m.type=='control_change' and m.channel==0 and m.control==64 and m.value==0 for m in out.messages)
        before=len(out.messages)
        player._dispatch_event(0,'on',mido.Message('note_on',channel=0,note=67,velocity=100),(0,'blocked'))
        assert len(out.messages)==before
        p.tracks[0].muted=False;player.set_track_states(p.tracks)
        assert player.playing and player.errors.empty()
    finally:player.stop()


def test_preview_unison_does_not_cut_sequenced_note():
    p=Project();out=Capture();player=Player()
    player._tracks=p.tracks;player._output=out;player._allowed=audible_tracks(p.tracks)
    player.playing=True;player._ready=True
    note=mido.Message('note_on',channel=0,note=60,velocity=90)
    player._dispatch_event(0,'on',note,(0,'sequence'))
    token=player.begin_preview(0,60,100)
    player.end_preview(token)
    assert [m.type for m in out.messages]==['note_on']
    player._dispatch_event(0,'off',note,(0,'sequence'))
    assert [m.type for m in out.messages]==['note_on','note_off']
    token=player.begin_preview(0,67,100);player.end_preview(token)
    assert out.messages[-1].type=='note_off' and out.messages[-1].note==67
    player.playing=False


def test_states_persist_in_project_without_discarding_smf_notes(tmp_path):
    p=Project();p.tracks[0].muted=True;p.tracks[1].solo=True
    p.tracks[0].notes=[Note(0,60,240)]
    path=tmp_path/'states.juno.json';project_io.save(p,path)
    q=project_io.load(path)
    assert q.tracks[0].muted and q.tracks[1].solo
    old=p.data()
    for t in old['tracks']:t.pop('muted');t.pop('solo')
    q=Project.from_data(old)
    assert not any(t.muted or t.solo for t in q.tracks)
    path=tmp_path/'states.mid';smf.save(p,path);q,_=smf.load(path)
    assert len(q.tracks[0].notes)==1
