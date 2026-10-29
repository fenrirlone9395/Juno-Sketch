"""Drum layout for the shared note editor; playback/storage stay MIDI notes."""
from services.drum_map import DRUM_LANES, DRUM_ROWS, drum_label


class DrumLayout:
    label_width = 210
    row_height = 24

    @staticmethod
    def row(pitch):
        return DRUM_ROWS[pitch]

    @staticmethod
    def pitch(row):
        return DRUM_LANES[row]

    @staticmethod
    def label(pitch):
        return drum_label(pitch)

    @staticmethod
    def color(pitch):
        if pitch in (35, 36):return '#39434c'
        if pitch in (37, 38, 39, 40):return '#403d4b'
        if pitch in (42, 44, 46):return '#3a4646'
        return '#303742' if DRUM_ROWS[pitch] % 2 else '#262c35'
