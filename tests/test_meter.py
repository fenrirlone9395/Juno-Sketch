import pytest
from models.project import Project, Note
from services.meter import MeterMap, set_at_bar, remove_at_bar
from services import project_io
from midi import smf


@pytest.mark.parametrize('n,d,bar_ticks,beat_ticks',[(3,4,2880,960),(6,8,2880,480),(5,4,4800,960),(7,8,3360,480),(3,16,720,240)])
def test_meter_positions(n,d,bar_ticks,beat_ticks):
    meter=MeterMap([[0,n,d]])
    assert meter.bar_start(2)==bar_ticks
    assert meter.position(bar_ticks)==(2,1,0,n,d)
    assert meter.position(beat_ticks)==(1,2,0,n,d)
    assert len(list(meter.beats(0,bar_ticks)))==n


def test_meter_changes_and_preserving_bar_numbers():
    signatures=set_at_bar([[0,4,4]],5,3,4)
    assert signatures==[[0,4,4],[15360,3,4]]
    changed=set_at_bar(signatures,1,6,8)
    assert changed==[[0,6,8],[11520,3,4]]
    meter=MeterMap(changed)
    assert meter.position(11520)==(5,1,0,3,4)
    assert meter.bar_start(6)==14400
    assert remove_at_bar(changed,5)==[[0,6,8]]
    with pytest.raises(ValueError):remove_at_bar(changed,1)


def test_midbar_import_and_grid_anchor():
    meter=MeterMap([[0,4,4],[1000,7,8]])
    assert meter.bar_start(2)==1000
    assert meter.position(1000)==(2,1,0,7,8)
    meter=MeterMap([[0,3,16]])
    assert meter.snap(721,160)==720
    assert meter.snap(870,160)==880
    ticks=list(meter.grid_ticks(1440,160))
    assert 720 in ticks and 880 in ticks and 800 not in ticks


def test_project_smf_mixed_meter_roundtrip(tmp_path):
    p=Project()
    p.signatures=set_at_bar([[0,6,8]],5,7,8)
    p.tracks[0].notes=[Note(11000,60,3000)]
    path=tmp_path/'meters.juno.json';project_io.save(p,path)
    assert project_io.load(path).signatures==p.signatures
    path=tmp_path/'meters.mid';smf.save(p,path)
    q,warnings=smf.load(path)
    assert not warnings
    assert q.signatures==p.signatures
    assert q.tracks[0].notes[0].start==11000
    assert q.tracks[0].notes[0].duration==3000


@pytest.mark.parametrize('signatures',[[[0,0,4]],[[0,4,3]],[[-1,4,4]],[[0,4,512]]])
def test_invalid_signatures(signatures):
    with pytest.raises(ValueError):MeterMap(signatures)
