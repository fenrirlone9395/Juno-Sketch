"""PPQ-based musical positions, including imported meter changes."""
from bisect import bisect_right
from dataclasses import dataclass
from models.project import PPQ

DENOMINATORS = (1, 2, 4, 8, 16, 32, 64, 128, 256)


@dataclass(frozen=True)
class Segment:
    tick: int
    bar: int
    numerator: int
    denominator: int

    @property
    def beat_ticks(self):
        return PPQ * 4 // self.denominator

    @property
    def bar_ticks(self):
        return self.numerator * self.beat_ticks


class MeterMap:
    def __init__(self, signatures):
        events = {0: (4, 4)}
        for event in signatures:
            if len(event) != 3:
                raise ValueError('不正な拍子情報です')
            tick, n, d = event
            if (any(not isinstance(v, int) or isinstance(v, bool) for v in event)
                    or tick < 0 or not 1 <= n <= 255 or d not in DENOMINATORS):
                raise ValueError('拍子は分子1〜255、分母は1〜256の2の累乗で指定してください')
            events[tick] = (n, d)
        self.segments = []
        for tick, (n, d) in sorted(events.items()):
            if not self.segments:
                bar = 1
            else:
                previous = self.segments[-1]
                # An imported mid-bar change closes the partial bar.
                bar = previous.bar + (tick-previous.tick+previous.bar_ticks-1)//previous.bar_ticks
            self.segments.append(Segment(tick, bar, n, d))
        self.starts = [s.tick for s in self.segments]
        self.bars = [s.bar for s in self.segments]

    def segment(self, tick):
        return self.segments[max(0, bisect_right(self.starts, tick)-1)]

    def position(self, tick):
        tick = max(0, int(tick))
        s = self.segment(tick)
        bar_offset, within = divmod(tick-s.tick, s.bar_ticks)
        beat, remainder = divmod(within, s.beat_ticks)
        return s.bar+bar_offset, beat+1, remainder, s.numerator, s.denominator

    def bar_start(self, bar):
        if bar < 1:
            raise ValueError('小節番号は1以上です')
        s = self.segments[max(0, bisect_right(self.bars, bar)-1)]
        return s.tick+(bar-s.bar)*s.bar_ticks

    def beats(self, start, end):
        for i, s in enumerate(self.segments):
            stop = min(end, self.starts[i+1] if i+1 < len(self.starts) else end)
            tick = s.tick+max(0, (max(start, s.tick)-s.tick)//s.beat_ticks)*s.beat_ticks
            while tick < stop:
                bar, beat, _, _, _ = self.position(tick)
                yield tick, bar, beat, s.numerator, s.denominator
                tick += s.beat_ticks

    def extent(self, end_tick, minimum_bars=8):
        bars = max(minimum_bars, self.position(end_tick)[0]+1)
        return self.bar_start(bars+1)

    def grid_ticks(self, end, step):
        bar = 1
        while self.bar_start(bar) < end:
            start, stop = self.bar_start(bar), min(end,self.bar_start(bar+1))
            yield from range(start,stop,step)
            bar += 1

    def snap(self, tick, step):
        tick = max(0, round(tick))
        bar = self.position(tick)[0]
        start = self.bar_start(bar)
        snapped = start+int((tick-start+step/2)//step)*step
        return min(snapped, self.bar_start(bar+1))


def set_at_bar(signatures, bar, numerator, denominator):
    """Preserve later meter changes at their musical bar numbers."""
    MeterMap([[0,numerator,denominator]])
    current = MeterMap(signatures)
    by_bar = {s.bar: (s.numerator, s.denominator) for s in current.segments}
    by_bar[bar] = (numerator, denominator)
    return from_bars(by_bar)


def from_bars(by_bar):
    result = []
    tick, previous_bar, previous_n, previous_d = 0, 1, 4, 4
    for event_bar, (n, d) in sorted(by_bar.items()):
        if not isinstance(event_bar, int) or event_bar < 1:
            raise ValueError('小節番号は1以上です')
        tick += (event_bar-previous_bar)*previous_n*(PPQ*4//previous_d)
        result.append([tick, n, d])
        previous_bar, previous_n, previous_d = event_bar, n, d
    MeterMap(result)  # Validate before any caller mutates the project.
    return result


def remove_at_bar(signatures, bar):
    if bar == 1:
        raise ValueError('先頭の拍子は削除できません。別の拍子を設定してください')
    by_bar = {s.bar: (s.numerator, s.denominator) for s in MeterMap(signatures).segments}
    by_bar.pop(bar, None)
    return from_bars(by_bar)
