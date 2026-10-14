"""V26 wire values and state gates, independent of sockets and widgets."""
from dataclasses import dataclass, asdict
import re

RATE = 100_000_000
ERROR_MASK = 0x1810
COMPARISONS = ('≥', '>', '=', '≤', '<')


@dataclass(frozen=True)
class AcquisitionSettings:
    len_mode: int = 0
    length: int = 10
    pre: int = 30
    mode: int = 0
    vth: int = 2500
    vcmp: int = 0
    ith: int = 1500
    icmp: int = 4
    enable: int = 3
    gap_ms: int = 1000
    rate_msps: int = 100

    def __post_init__(self):
        limits = dict(len_mode=(0,1), length=(1,200 if self.len_mode == 0 else 20_000_000),
                      pre=(0,100), mode=(0,1), vth=(0,4095), vcmp=(0,4),
                      ith=(0,4095), icmp=(0,4), enable=(0,3), gap_ms=(0,600000), rate_msps=(1,100))
        for name, (low,high) in limits.items():
            value = getattr(self,name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f'{name} 必须为 {low}–{high} 的整数')
        if self.mode == 1 and self.enable == 0:
            raise ValueError('自动模式至少启用一个触发通道')

    @property
    def samples(self):
        return self.length * self.rate_msps * 1000 if self.len_mode == 0 else self.length

    @property
    def pre_samples(self):
        return self.samples * self.pre // 100

    def command(self, verb='CFG', *, include_rate=True):
        if verb not in ('CFG','ACQ'):
            raise ValueError('配置命令必须为 CFG 或 ACQ')
        values=list(asdict(self).values())
        if not include_rate:
            if self.rate_msps!=100:raise ValueError('设备未提供可调保存速率；只能使用 100 MSPS')
            values=values[:-1]
        return (verb+' '+','.join(str(v) for v in values)+'\r').encode('ascii')

    def matches(self, status):
        expected = dict(LENMODE=self.len_mode,
                        PRE=self.pre, MODE=self.mode, VTH=self.vth, VCMP=self.vcmp,
                        ITH=self.ith, ICMP=self.icmp, ENABLE=self.enable, GAP_MS=self.gap_ms)
        if self.len_mode==0:
            expected['TIME']=self.length
            # V28 CFG_SAMPLES is the point-count register, not time-mode N.
            if 'CFG_RATE_MSPS' not in status:expected['CFG_SAMPLES']=self.samples
        else:expected['CFG_SAMPLES']=self.samples
        if 'CFG_RATE_MSPS' in status:expected['CFG_RATE_MSPS']=self.rate_msps
        elif self.rate_msps!=100:return False
        return all(status.get(k) == v for k,v in expected.items())


def parse_fst(text):
    result = {}
    previous = None
    for token in text.strip().split(','):
        if ':' not in token:
            if previous != 'SET':
                raise ValueError('状态回包中出现无字段名的值')
            result[previous] += ','+token.strip()
            previous = None
            continue
        name, value = (part.strip() for part in token.split(':',1))
        if not re.fullmatch(r'[A-Z][A-Z0-9_]*',name) or name in result:
            raise ValueError('状态字段名非法或重复：'+name)
        result[name] = value
        previous = name
    return result


def parse_tst(text):
    fields = parse_fst(text)
    required = ('STATUS EVENTS TRIGGER ARMED HISTORY_READY TRIGGERED ABORTED REASON CTRL '
                'PENDING LENMODE TIME CFG_SAMPLES PRE MODE VTH VCMP ITH ICMP ENABLE '
                'ACTIVE_PRE RATE SAMPLES TOTAL BLOCKS').split()
    required.append('HEX_CHARS')
    missing = set(required)-fields.keys()
    if missing:
        raise ValueError('TST 缺少字段：'+','.join(sorted(missing)))
    result = {}
    for name,value in fields.items():
        base = 16 if name in ('STATUS','EVENTS','TRIGGER') else 10
        if not re.fullmatch(r'[0-9A-Fa-f]{4}' if base == 16 else r'[0-9]+',value):
            raise ValueError('TST 字段数值格式错误：'+name)
        result[name] = int(value,base)
    return result


def can_arm(s):
    return (s.get('STATUS',0)&0x2061)==0x2061 and not s.get('STATUS',0)&ERROR_MASK and s.get('PENDING')==0 and s.get('CTRL')==0


def can_get(s):
    return (s.get('STATUS',0)&0x008C)==0x008C and not s.get('STATUS',0)&ERROR_MASK and s.get('PENDING')==1 and s.get('CTRL')==0


def can_force(s, active):
    return (active is not None and active.mode==0 and s.get('CTRL')==0
            and s.get('STATUS',0)&2 and not s.get('STATUS',0)&(ERROR_MASK|4)
            and s.get('ARMED')==1 and s.get('HISTORY_READY')==1 and s.get('TRIGGERED')==0)


def can_release(s):
    status=s.get('STATUS',0)
    return bool(s.get('CTRL')==0 and status&4 and not status&(2|0x100) and status&(0x80|0x400|0x10))


def record_rate_hz(s):
    """Use the latched save rate, never V28 RATE (the original ADC clock)."""
    if 'CFG_RATE_MSPS' in s or 'ACTIVE_RATE_MSPS' in s:
        rate=s.get('ACTIVE_RATE_MSPS')
        if type(rate) is not int or not 1<=rate<=100:
            raise ValueError('记录缺少有效 ACTIVE_RATE_MSPS 保存速率')
        return rate*1_000_000
    return RATE


def validate_record(s, active=None):
    n=s['SAMPLES']
    if not (1 <= n <= 20_000_000 and s['TOTAL']==n*4 and s['HEX_CHARS']==n*8
            and s['BLOCKS']==(n*4+8191)//8192 and 0 <= s['ACTIVE_PRE'] <= n and s['RATE']==RATE):
        raise ValueError('记录元数据不一致：SAMPLES/TOTAL/HEX_CHARS/BLOCKS/ACTIVE_PRE/RATE')
    saved_rate=record_rate_hz(s)
    if active is not None and (n != active.samples or s['ACTIVE_PRE'] != active.pre_samples
                               or saved_rate != active.rate_msps*1_000_000):
        raise ValueError('完成记录与本次启动的长度/前触发位置/保存速率不一致')


def reason_text(reason):
    return ' + '.join(name for bit,name in ((1,'电压'),(2,'电流'),(4,'手动')) if reason&bit) or '未知/尚未完成'
