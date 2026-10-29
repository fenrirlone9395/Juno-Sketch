from collections import defaultdict, deque
import mido
from models.project import Project, Note, PPQ

def save(project, path):
    f = mido.MidiFile(type=1, ticks_per_beat=PPQ)
    conductor = mido.MidiTrack()
    f.tracks.append(conductor)
    events = [(0, mido.MetaMessage('set_tempo', tempo=mido.bpm2tempo(project.bpm)))]
    events += [(int(t), mido.MetaMessage('set_tempo', tempo=int(v))) for t,v in project.tempos if t>0]
    events += [(int(t), mido.MetaMessage('time_signature', numerator=n, denominator=d)) for t,n,d in project.signatures]
    _write(conductor, events)
    for track in project.tracks:
        out = mido.MidiTrack()
        f.tracks.append(out)
        ch = track.channel
        events = [(0, mido.MetaMessage('track_name', name=track.name))]
        events += [(0, mido.Message('control_change', channel=ch, control=c, value=v)) for c,v in ((0,track.msb),(32,track.lsb))]
        events.append((0, mido.Message('program_change', channel=ch, program=track.program)))
        for tick, data in track.events:
            events.append((tick, mido.Message.from_dict(data)))
        for note in track.notes:
            events.extend([(note.start, mido.Message('note_on', channel=ch, note=note.pitch, velocity=note.velocity)),
                           (note.start+note.duration, mido.Message('note_off', channel=ch, note=note.pitch))])
        _write(out, events)
    f.save(path)

def _write(track, events):
    # Keep bank/program order stable; note-offs precede note-ons at boundaries.
    events.sort(key=lambda e: (e[0], 0 if e[1].type=='note_off' else 1))
    previous = 0
    for tick, message in events:
        track.append(message.copy(time=tick-previous))
        previous = tick
    track.append(mido.MetaMessage('end_of_track'))

def load(path):
    f = mido.MidiFile(path)
    if f.type == 2 or f.ticks_per_beat <= 0:
        raise ValueError('SMF Type 0/1 (PPQ) のみ対応しています')
    p = Project()
    p.signatures, p.tempos = [], []
    slots = {}
    warnings = []
    def scaled(t):
        return round(t*PPQ/f.ticks_per_beat)
    for ti, source in enumerate(f.tracks):
        tick, name = 0, ''
        active = defaultdict(deque)
        touched = set()
        for m in source:
            tick += m.time
            t = scaled(tick)
            if m.type == 'track_name':
                name = m.name
            if m.type == 'set_tempo':
                p.tempos.append([t,m.tempo])
            if m.type == 'time_signature':
                p.signatures.append([t,m.numerator,m.denominator])
            if m.is_meta or not hasattr(m, 'channel'):
                continue
            key = (ti,m.channel)
            if key not in slots:
                if len(slots) >= 16:
                    raise ValueError('16を超えるトラック/チャンネルがあります。読み込みを中止しました')
                slots[key] = len(slots)
                tr = p.tracks[slots[key]]
                tr.channel = m.channel
                tr.msb = 120 if m.channel == 9 else 121
                tr.lsb = 0
                tr.name = name or f'Track {slots[key]+1:02}'
            tr = p.tracks[slots[key]]
            touched.add(key)
            if m.type=='note_on' and m.velocity:
                active[(key,m.note)].append((t,m.velocity))
            elif m.type=='note_off' or (m.type=='note_on' and m.velocity==0):
                q = active[(key,m.note)]
                if q:
                    start,vel=q.popleft()
                    tr.notes.append(Note(start,m.note,max(1,t-start),vel))
            elif m.type in ('control_change','program_change','pitchwheel','aftertouch','polytouch'):
                initial = t==0 and (m.type=='program_change' or (m.type=='control_change' and m.control in (0,32)))
                if initial:
                    if m.type=='program_change': tr.program=m.program
                    elif m.control==0: tr.msb=m.value
                    else: tr.lsb=m.value
                else:
                    tr.events.append([t,m.copy(time=0).dict()])
        for (key,pitch),queue in active.items():
            for start,vel in queue:
                p.tracks[slots[key]].notes.append(Note(start,pitch,max(1,scaled(tick)-start),vel))
                warnings.append('Note Offのないノートをトラック終端で閉じました')
    p.tempos.sort()
    if p.tempos and p.tempos[0][0]==0:
        p.bpm = mido.tempo2bpm(p.tempos[0][1])
    if not p.signatures: p.signatures=[[0,4,4]]
    if any(n!=4 or d!=4 for _,n,d in p.signatures):
        warnings.append('拍子情報は保存・再生時に保持しますが、エディターの小節線は4/4表示です')
    p.ui['bars'] = max(8, 1+max((n.start+n.duration for tr in p.tracks for n in tr.notes),default=0)//(4*PPQ))
    return p, list(dict.fromkeys(warnings))
