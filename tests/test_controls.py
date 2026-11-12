from copy import deepcopy
import time
import pytest
import mido
from models.project import Project, Note
from services.controllers import put_cc, cc_value, cc_events, sustain
from services.sysex import parse_hex,format_hex
from services import project_io
from midi import smf
from midi.player import Player
from midi.internal_preview import InternalPreviewOutput
from midi.output import MidiOutput
from test_core import Capture


def test_cc_replace_template_preserves_other_events():
    p=Project();t=p.tracks[3]
    put_cc(t,0,7,83);put_cc(t,0,7,92)
    assert cc_value(t,7)==92 and len(cc_events(t,7))==1
    put_cc(t,100,64,0);put_cc(t,200,64,127);put_cc(t,250,10,32)
    sustain(t,100,300)
    assert [(tick,value) for _,tick,value in cc_events(t,64)]==[(100,127),(300,0)]
    assert cc_value(t,10,250)==32
    assert all(data['channel']==3 for _,data in t.events)
    before=deepcopy(t.events)
    with pytest.raises(ValueError):sustain(t,300,100)
    assert t.events==before
    with pytest.raises(ValueError):put_cc(t,0,32,0)


@pytest.mark.parametrize('text',['F0 41 F7','41 10 00','f0 7e 7f 09 01 f7'])
def test_sysex_hex_roundtrip(text):
    data=parse_hex(text);assert parse_hex(format_hex(data))==data


@pytest.mark.parametrize('text',['','F0 F7','F0 41','41 F7','F0 80 F7','F0 GG F7','F0 4 F7','F0 41 F0 F7'])
def test_sysex_rejects_invalid_bytes(text):
    with pytest.raises(ValueError):parse_hex(text)


def test_project_smf_cc_sysex_and_legacy(tmp_path):
    p=Project();put_cc(p.tracks[0],0,7,80);sustain(p.tracks[0],100,300)
    p.sysex=[dict(tick=0,data=[0x7e,0x7f,9,1],label='GM On'),dict(tick=240,data=[0x41,0x10,0],label='Test')]
    project_io.save(p,tmp_path/'x.json');q=project_io.load(tmp_path/'x.json')
    assert p.data()==q.data()
    smf.save(p,tmp_path/'x.mid');q,_=smf.load(tmp_path/'x.mid')
    assert [(e['tick'],e['data']) for e in q.sysex]==[(e['tick'],e['data']) for e in p.sysex]
    assert q.tracks[0].events==p.tracks[0].events
    legacy=p.data();legacy.pop('sysex');legacy['ui'].pop('master_volume')
    assert Project.from_data(legacy).sysex==[]
    bad=p.data();bad['sysex'][0]['data']=[128]
    with pytest.raises(ValueError):Project.from_data(bad)


def test_sysex_playback_seek_and_cc_chase():
    p=Project(bpm=400);p.tracks[0].notes=[Note(0,60,480)]
    sustain(p.tracks[0],0,480)
    p.sysex=[dict(tick=0,data=[0x41,1],label='before'),dict(tick=400,data=[0x41,2],label='after')]
    out=Capture();player=Player();player.start(p,out,start=240);player.thread.join(1)
    assert not player.playing and player.errors.empty()
    assert [list(m.data) for m in out.messages if m.type=='sysex']==[[0x41,2]]
    assert any(m.type=='control_change' and m.control==64 and m.value==127 for m in out.messages)


def test_live_mixer_does_not_stop_playback():
    p=Project();p.tracks[0].notes=[Note(0,60,9600)]
    out=Capture();player=Player();player.start(p,out)
    deadline=time.monotonic()+1
    while not player._ready and time.monotonic()<deadline:time.sleep(.002)
    try:
        put_cc(p.tracks[0],0,7,65)
        assert player.live_cc(0,7,65,p.tracks) and player.playing
        assert out.messages[-1].type=='control_change' and out.messages[-1].value==65
    finally:player.stop()


def test_native_master_is_audio_gain_and_sysex_is_ignored():
    out=InternalPreviewOutput.__new__(InternalPreviewOutput);MidiOutput.__init__(out)
    out.mixer=None;calls=[]
    out.set_parameter=lambda *args:calls.append(args) or 0
    out.set_master_volume(.25)
    assert calls==[(None,0,2,0,.25,0)]
    out.event=lambda *args:pytest.fail('SysEx must not go through short MIDI event API')
    out.send(mido.Message('sysex',data=[0x41,1]))
