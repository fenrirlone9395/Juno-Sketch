"""Drum layout preserves the complete MIDI note domain."""
from services.drum_map import DRUM_LANES, GM_DRUM_NAMES, drum_label
from ui.drum_editor import DrumLayout
from models.project import Project


def test_drum_map_and_reversible_layout():
    assert len(GM_DRUM_NAMES)==47
    assert GM_DRUM_NAMES[36]=='Bass Drum 1'
    assert GM_DRUM_NAMES[38]=='Acoustic Snare'
    assert GM_DRUM_NAMES[42]=='Closed Hi-Hat'
    assert len(DRUM_LANES)==128 and set(DRUM_LANES)==set(range(128))
    assert DRUM_LANES[:3]==(35,36,37)
    for pitch in range(128):assert DrumLayout.pitch(DrumLayout.row(pitch))==pitch
    assert drum_label(0)=='000  Note 0'
    p=Project();p.ui['view']='Drum Editor'
    assert Project.from_data(p.data()).ui['view']=='Drum Editor'
