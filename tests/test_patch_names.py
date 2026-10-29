from collections import Counter
from models.project import Project, Track
from services.patch_names import lookup, apply_name, patch_map
from services import project_io
from midi import smf


def test_factory_map_addresses_and_coverage():
    patches=patch_map()
    assert len(patches)==1567
    assert Counter((p['bank'],p['msb']) for p in patches.values())=={
        ('DS',87):184,('PRST',87):1088,('GM',121):256,
        ('DS',86):9,('PRST',86):21,('GM',120):9}
    assert lookup(87,73,0)['name']=='Grand Pno DS'
    assert lookup(87,64,0)['name']=='88StageGrand'
    assert lookup(121,0,0)['name']=='Piano 1'
    assert lookup(121,1,0)['name']=='Piano 1w'
    assert lookup(86,65,0)['name']=='StudioKt DS1'
    assert lookup(120,0,0)['name']=='GM2 STANDARD'
    # Unknown/user banks are never guessed from just PC.
    assert lookup(0,0,0) is None
    assert lookup(87,0,0) is None
    assert all(0<=value<=127 for key in patches for value in key)


def test_name_application_and_persistence(tmp_path):
    p=Project();t=p.tracks[0]
    t.msb,t.lsb,t.program=87,73,0
    t.auto_name=True
    assert apply_name(t) and t.name=='Grand Pno DS'
    t.msb=0
    assert not apply_name(t) and t.name=='Grand Pno DS'
    path=tmp_path/'named.juno.json';project_io.save(p,path)
    assert project_io.load(path).tracks[0].auto_name
    assert project_io.load(path).tracks[0].name=='Grand Pno DS'
    data=p.data();data['tracks'][0].pop('auto_name')
    assert not Project.from_data(data).tracks[0].auto_name


def test_factory_names_are_smf_safe(tmp_path):
    # The PDF's typographic apostrophes must not break MIDI's default Latin-1.
    assert all(patch['name'].isascii() for patch in patch_map().values())
    p=Project();p.tracks[0].name=lookup(87,73,0)['name']
    path=tmp_path/'named.mid';smf.save(p,path)
    restored,_=smf.load(path)
    assert restored.tracks[0].name==p.tracks[0].name
