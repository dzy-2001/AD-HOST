"""Original-sample cursor values and view ranges, independent of Qt."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class SamplePoint:
    index: int
    time_ms: float
    voltage: float
    current: int


def _coordinate(recording,time_ms):
    if not math.isfinite(time_ms):raise ValueError('时间坐标必须为有限值')
    return time_ms*recording.sample_rate_hz/1000+(recording.trigger_index or 0)


def sample_at(recording,time_ms):
    index=max(0,min(len(recording.samples)-1,int(math.floor(_coordinate(recording,time_ms)+.5))))
    raw=recording.samples[index]
    return SamplePoint(index,(index-(recording.trigger_index or 0))*1000/recording.sample_rate_hz,
                       int(raw[0])*12/4096-6,int(raw[1]))


def visible_range(recording,left,right):
    a,b=sorted((_coordinate(recording,left),_coordinate(recording,right)))
    count=len(recording.samples)
    start=max(0,min(count-1,math.floor(a)))
    stop=max(start+1,min(count,math.ceil(b)+1))
    return start,stop


def measurement(a,b):
    return dict(samples=b.index-a.index,time_ms=b.time_ms-a.time_ms,
                voltage=b.voltage-a.voltage,current=b.current-a.current)
