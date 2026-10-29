from copy import deepcopy
import mido
from models.project import Project
from services.output_mode import switch_destination, default_bank, INTERNAL, JUNO
from services.project_io import save, load
from midi.internal_preview import InternalPreviewOutput
from midi.output import MidiOutput
from midi import smf


def test_initial_gm_and_juno_defaults():
    p=Project()
    assert (p.tracks[0].msb,p.tracks[0].lsb)==(121,0)
    assert (p.tracks[9].msb,p.tracks[9].lsb)==(120,0)
    p.tracks[0].program=24
    assert switch_destination(p,JUNO)
    assert (p.tracks[0].msb,p.tracks[0].lsb,p.tracks[0].program)==(87,64,24)
    assert (p.tracks[9].msb,p.tracks[9].lsb)==(86,64)


def test_switch_recall_name_follow_and_persistence(tmp_path):
    p=Project();p.tracks[0].auto_name=True
    p.tracks[0].events=[[100,mido.Message('program_change',program=2).dict()]]
    events=deepcopy(p.tracks[0].events)
    switch_destination(p,JUNO)
    assert p.tracks[0].name=='88StageGrand'
    p.tracks[0].msb,p.tracks[0].lsb=87,73
    switch_destination(p,INTERNAL)
    assert (p.tracks[0].msb,p.tracks[0].lsb,p.tracks[0].name)==(121,0,'Piano 1')
    path=tmp_path/'routing.juno.json';save(p,path);p=load(path)
    switch_destination(p,JUNO)
    assert (p.tracks[0].msb,p.tracks[0].lsb,p.tracks[0].name)==(87,73,'Grand Pno DS')
    assert p.tracks[0].events==events
    before=p.data()
    assert not switch_destination(p,JUNO)
    assert p.data()==before


def test_native_preview_receives_base_bank_messages():
    output=InternalPreviewOutput.__new__(InternalPreviewOutput)
    MidiOutput.__init__(output)
    output.unit=None;received=[]
    def event(unit,status,a,b,offset):
        received.append((status,a,b));return 0
    output.event=event
    p=Project()
    output.setup(p.tracks[0]);output.setup(p.tracks[9])
    assert received[:3]==[(0xB0,0,121),(0xB0,32,0),(0xC0,0,0)]
    assert received[3:]==[(0xB9,0,120),(0xB9,32,0),(0xC9,0,0)]
    output.send(mido.Message('control_change',channel=0,control=0,value=87))
    output.send(mido.Message('control_change',channel=0,control=32,value=73))
    assert received[-2:]==[(0xB0,0,121),(0xB0,32,0)]


def test_smf_without_banks_on_channel_ten(tmp_path):
    f=mido.MidiFile(type=0)
    f.tracks.append(mido.MidiTrack([mido.Message('note_on',channel=9,note=36,velocity=90),
                                   mido.Message('note_off',channel=9,note=36,time=120)]))
    path=tmp_path/'drums.mid';f.save(path)
    p,_=smf.load(path)
    assert (p.tracks[0].channel,p.tracks[0].msb,p.tracks[0].lsb)==(9,120,0)
