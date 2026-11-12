"""Strict, seven-bit SysEx parsing. F0/F7 are displayed but not stored in data."""
import re
import mido


def parse_hex(text):
    parts=text.split()
    if not parts:raise ValueError('SysExの16進バイト列を入力してください')
    if any(not re.fullmatch(r'[0-9a-fA-F]{2}',p) for p in parts):
        raise ValueError('各バイトを2桁の16進数で入力し、空白で区切ってください')
    values=[int(p,16) for p in parts]
    if values[0]==0xf0 or values[-1]==0xf7:
        if values[0]!=0xf0 or values[-1]!=0xf7:
            raise ValueError('F0とF7は両方を指定してください')
        values=values[1:-1]
    if not values or any(v>127 for v in values):
        raise ValueError('SysExデータは1個以上の00〜7Fです（F0/F7は外側のみ）')
    return list(mido.Message('sysex',data=values).data)


def format_hex(data):
    return ' '.join(f'{b:02X}' for b in [0xf0,*data,0xf7])


def validate(events):
    if not isinstance(events,list):raise ValueError('不正なSysEx一覧です')
    for event in events:
        if not isinstance(event,dict) or set(event)!={'tick','data','label'}:
            raise ValueError('不正なSysExイベントです')
        if type(event['tick']) is not int or event['tick']<0 or not isinstance(event['label'],str):
            raise ValueError('不正なSysEx位置・名前です')
        data=event['data']
        if not isinstance(data,list) or not data or any(type(b) is not int or not 0<=b<=127 for b in data):
            raise ValueError('SysExデータは00〜7Fの整数です')
