"""Controller edits operate on the same events used by SMF and playback."""
import mido

CC_NAMES={1:'Modulation',7:'Volume',10:'Pan',11:'Expression',64:'Sustain',
          65:'Portamento',66:'Sostenuto',67:'Soft pedal',91:'Reverb',93:'Chorus'}


def cc_events(track,control):
    return [(i,tick,data['value']) for i,(tick,data) in enumerate(track.events)
            if data.get('type')=='control_change' and data.get('control')==control]


def put_cc(track,tick,control,value):
    if not isinstance(tick,int) or tick<0:raise ValueError('tickは0以上の整数です')
    message=mido.Message('control_change',channel=track.channel,control=control,value=value)
    # Bank select lives in the track settings; avoid competing representations.
    if control in (0,32):raise ValueError('Bank Selectはトラック設定で編集してください')
    track.events[:]=[[t,d] for t,d in track.events
                    if not (t==tick and d.get('type')=='control_change' and d.get('control')==control)]
    track.events.append([tick,message.dict()]);track.events.sort(key=lambda e:e[0])


def cc_value(track,control,tick=0,default=None):
    value=default if default is not None else (100 if control==7 else 64 if control==10 else 0)
    for _,time,v in sorted(cc_events(track,control),key=lambda e:e[1]):
        if time>tick:break
        value=v
    return value


def sustain(track,start,end,on=True):
    if not isinstance(start,int) or not isinstance(end,int) or not 0<=start<end:
        raise ValueError('開始tickより後の終了tickを指定してください')
    # A region template replaces CC64 inside its span and always closes the pedal.
    track.events[:]=[[t,d] for t,d in track.events
                    if not (start<=t<=end and d.get('type')=='control_change' and d.get('control')==64)]
    put_cc(track,start,64,127 if on else 0)
    put_cc(track,end,64,0)
