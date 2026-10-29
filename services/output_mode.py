"""Destination bank defaults and per-track JUNO bank recall."""
from services.patch_names import apply_name

INTERNAL = 'Internal Preview'
JUNO = 'JUNO-DS'


def is_drum(track):
    return track.channel == 9 or track.msb in (86, 120)


def default_bank(destination, drum=False):
    if destination == INTERNAL:
        return (120 if drum else 121), 0
    if destination == JUNO:
        return (86 if drum else 87), 64
    raise ValueError('未対応の出力先です')


def switch_destination(project, destination):
    """Switch once, not on MIDI port changes. PC/events/notes remain unchanged.

    Internal is always the GM base bank. JUNO recalls the last manually
    configured bank; its first use starts at PRST. Bank snapshots are saved
    inside each track so project I/O and Undo remain self-contained.
    """
    if destination not in (INTERNAL, JUNO):
        raise ValueError('未対応の出力先です')
    previous = project.ui['output']
    if previous == destination:
        return False
    for track in project.tracks:
        if previous == JUNO:
            track.output_banks[JUNO] = [track.msb, track.lsb]
        bank = default_bank(destination, is_drum(track))
        if destination == JUNO:
            bank = track.output_banks.get(JUNO, bank)
        track.msb, track.lsb = bank
        if track.auto_name:
            apply_name(track)
    project.ui['output'] = destination
    return True
