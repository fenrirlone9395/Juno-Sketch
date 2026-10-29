"""GM percussion reference names, not a JUNO kit-specific assignment table.

Reference: manufacturer's GM note assignment table:
https://downloads.monoprice.com/files/manuals/625889_Manual_200630.pdf
All other note numbers remain editable with numeric labels.
"""
_NAMES = '''Acoustic Bass Drum
Bass Drum 1
Side Stick
Acoustic Snare
Hand Clap
Electric Snare
Low Floor Tom
Closed Hi-Hat
High Floor Tom
Pedal Hi-Hat
Low Tom
Open Hi-Hat
Low-Mid Tom
Hi-Mid Tom
Crash Cymbal 1
High Tom
Ride Cymbal 1
Chinese Cymbal
Ride Bell
Tambourine
Splash Cymbal
Cowbell
Crash Cymbal 2
Vibraslap
Ride Cymbal 2
Hi Bongo
Low Bongo
Mute Hi Conga
Open Hi Conga
Low Conga
High Timbale
Low Timbale
High Agogo
Low Agogo
Cabasa
Maracas
Short Whistle
Long Whistle
Short Guiro
Long Guiro
Claves
Hi Wood Block
Low Wood Block
Mute Cuica
Open Cuica
Mute Triangle
Open Triangle'''.splitlines()
GM_DRUM_NAMES = dict(enumerate(_NAMES, 35))
# GM lanes first; retain every MIDI key for non-GM kits/imported material.
DRUM_LANES = tuple(range(35, 82)) + tuple(range(35)) + tuple(range(82, 128))
DRUM_ROWS = {pitch: row for row, pitch in enumerate(DRUM_LANES)}


def drum_label(pitch):
    return f'{pitch:03}  {GM_DRUM_NAMES.get(pitch, "Note " + str(pitch))}'
