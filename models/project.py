from dataclasses import dataclass, field, asdict
from uuid import uuid4

PPQ = 960
GRIDS = {f'1/{d}{suffix}': PPQ * 4 // d * (2 if suffix else 3) // 3
         for d in (4, 8, 16, 32) for suffix in ('', 'T')}

@dataclass
class Note:
    start: int
    pitch: int
    duration: int
    velocity: int = 100
    id: str = field(default_factory=lambda: uuid4().hex)

@dataclass
class Track:
    name: str = 'Track'
    channel: int = 0
    msb: int = 0
    lsb: int = 0
    program: int = 0
    velocity: int = 100
    notes: list[Note] = field(default_factory=list)
    events: list = field(default_factory=list)
    auto_name: bool = False
    muted: bool = False
    solo: bool = False
    output_banks: dict = field(default_factory=dict)

@dataclass
class Project:
    bpm: float = 120
    tracks: list[Track] = field(default_factory=lambda: [Track(f'Track {i+1:02}', i, msb=120 if i==9 else 121) for i in range(16)])
    tempos: list = field(default_factory=list)
    signatures: list = field(default_factory=lambda: [[0, 4, 4]])
    ui: dict = field(default_factory=lambda: dict(grid='1/16', mode='Grid', selected=0, output='Internal Preview', port='', bars=8, show_ghosts=True, view='Piano Roll', follow_playhead=True, track_selection=[0], zoom_x=1.0, zoom_y=1.0, wheel_horizontal=False))

    def data(self):
        return asdict(self)

    @classmethod
    def from_data(cls, data):
        p = cls()
        p.bpm = float(data['bpm'])
        if not 20 <= p.bpm <= 400 or len(data['tracks']) != 16:
            raise ValueError('BPMは20〜400、トラック数は16が必要です')
        p.tracks = []
        for t in data['tracks']:
            t = dict(t)
            t['notes'] = [Note(**n) for n in t['notes']]
            track = Track(**t)
            if not (0 <= track.channel <= 15 and all(0 <= x <= 127 for x in (track.msb, track.lsb, track.program)) and 1 <= track.velocity <= 127):
                raise ValueError('不正なトラック設定です')
            if any(not isinstance(v, bool) for v in (track.auto_name, track.muted, track.solo)):
                raise ValueError('不正な音色名追従設定です')
            if not isinstance(track.output_banks, dict):
                raise ValueError('不正な出力別バンク設定です')
            for destination, bank in track.output_banks.items():
                if (destination != 'JUNO-DS' or not isinstance(bank, list) or len(bank) != 2
                        or any(not isinstance(v, int) or not 0 <= v <= 127 for v in bank)):
                    raise ValueError('不正な出力別バンク設定です')
            for n in track.notes:
                if not (n.start >= 0 and n.duration >= 1 and 0 <= n.pitch <= 127 and 1 <= n.velocity <= 127):
                    raise ValueError('不正なノートです')
            p.tracks.append(track)
        p.ui.update(data.get('ui', {}))
        if p.ui['grid'] not in GRIDS or p.ui['mode'] not in ('Grid', 'Slip') or not 0 <= p.ui['selected'] < 16:
            raise ValueError('不正なUI設定です')
        if (p.ui['view'] not in ('Piano Roll', 'Drum Editor', 'All Tracks')
                or not isinstance(p.ui['show_ghosts'], bool)
                or not isinstance(p.ui['follow_playhead'], bool)):
            raise ValueError('不正な表示設定です')
        if 'track_selection' not in data.get('ui', {}):
            p.ui['track_selection'] = [p.ui['selected']]
        selection = p.ui['track_selection']
        if (not isinstance(selection,list) or not selection
                or any(not isinstance(i,int) or isinstance(i,bool) or not 0<=i<16 for i in selection)):
            raise ValueError('不正なトラック選択です')
        for key, low, high in (('zoom_x',0.25,4.0),('zoom_y',0.5,2.5)):
            value = p.ui[key]
            if not isinstance(value,(int,float)) or not low<=value<=high:
                raise ValueError('不正なズーム倍率です')
        if not isinstance(p.ui['wheel_horizontal'],bool):
            raise ValueError('不正なスクロール設定です')
        p.tempos = data.get('tempos', [])
        p.signatures = data.get('signatures', [[0,4,4]])
        from services.meter import MeterMap
        MeterMap(p.signatures)
        if p.ui['output'] not in ('Internal Preview', 'JUNO-DS'):
            raise ValueError('未対応の出力先です')
        for tick, tempo in p.tempos:
            if not (isinstance(tick, int) and tick >= 0 and 1 <= tempo <= 16777215):
                raise ValueError('不正なテンポ情報です')
        import mido
        for track in p.tracks:
            for tick, event in track.events:
                if not isinstance(tick, int) or tick < 0:
                    raise ValueError('不正なイベント位置です')
                message = mido.Message.from_dict(event)
                if message.type not in ('control_change', 'program_change', 'pitchwheel', 'aftertouch', 'polytouch'):
                    raise ValueError('未対応のMIDIイベントです')
        return p
