"""Loopback V26 device simulator. No ADC hardware is represented by this tool."""
import argparse
import select
import socket
import threading
import time


class Simulator:
    def __init__(self, port=0, *, fragment=0, fault=None, mbps=0):
        self.listener=socket.socket();self.listener.bind(('127.0.0.1',port));self.listener.listen(1)
        self.listener.settimeout(.2);self.port=self.listener.getsockname()[1]
        self.fragment=fragment;self.fault=fault;self.mbps=mbps
        self.stop_event=threading.Event();self.get_active=threading.Event()
        self.commands=[];self.interleaved=[];self.error=None
        self.arm_gate=None;self.arm_count=0
        self.config=[0,10,30,0,2500,0,1500,4,3,1000]
        self.active=None;self.phase='ready';self.polls=0;self.gap_until=0;self.conn=None
        self.thread=threading.Thread(target=self._serve,daemon=True);self.thread.start()

    def close(self):
        self.stop_event.set();self.listener.close()
        if self.conn:
            try:self.conn.shutdown(socket.SHUT_RDWR)
            except OSError:pass
        self.thread.join(3)

    def _send(self, conn, data):
        n=self.fragment or len(data)
        for i in range(0,len(data),n):conn.sendall(data[i:i+n])

    def status(self):
        c=self.config;a=self.active or c
        n=a[1]*100000 if a[0]==0 else a[1]
        done=self.phase=='done';busy=self.phase=='armed'
        status=0x20EC if done else 0x2062 if busy else 0x2061
        result=dict(STATUS=f'{status:04X}',EVENTS='0001',TRIGGER='0003' if busy else '0086' if done else '0000',
                    ARMED=int(busy),HISTORY_READY=int(self.polls>=2),TRIGGERED=int(done),ABORTED=0,
                    REASON=(4 if a[3]==0 else 1) if done else 0,CTRL=0,PENDING=int(busy or done),
                    LENMODE=c[0],TIME=c[1] if c[0]==0 else 0,CFG_SAMPLES=c[1]*100000 if c[0]==0 else c[1],
                    PRE=c[2],MODE=c[3],VTH=c[4],VCMP=c[5],ITH=c[6],ICMP=c[7],ENABLE=c[8],
                    ACTIVE_PRE=n*a[2]//100,RATE=100000000,SAMPLES=n if done else 0,TOTAL=n*4 if done else 0,
                    BLOCKS=(n*4+8191)//8192 if done else 0,DDR_WRITE_BURSTS=123,BURSTS_STABLE=1,HEX_CHARS=n*8 if done else 0,
                    GAP_MS=c[9],GAP_LEFT_MS=max(0,int((self.gap_until-time.monotonic())*1000)+1))
        if self.fault=='missing_gap':result.pop('GAP_LEFT_MS')
        return ','.join(f'{k}:{v}' for k,v in result.items()).encode()

    def _handle(self,conn,cmd):
        self.commands.append((cmd,time.monotonic()))
        name=cmd.split(' ',1)[0]
        ok=b'\r\n*';bad=b'\r\n?'
        if name=='VER':return b'V1.0.13 (V26)'+ok
        if name in ('FST','FREG'):return b'ID:ADFC,VER:0200,INIT:1,IERR:0,SET:10,1,HCLK:168000000,SDCLK:56000000'+ok
        if name=='TST':
            self.polls+=1
            if self.phase=='armed' and self.active[3]==1 and self.polls>=3:self.phase='done'
            return self.status()+ok
        if name in ('CFG','ACQ'):
            self.config=list(map(int,cmd.split(' ',1)[1].split(',')))
            if self.fault=='reject_cfg':return bad
            if name=='CFG':return ok
            name='ARM'
        if name=='ARM':
            if self.phase!='ready' or (self.config[3] and time.monotonic()<self.gap_until):return bad
            self.active=self.config.copy();self.phase='armed';self.polls=0
            self.arm_count+=1
            if self.arm_count==2 and self.arm_gate is not None:self.arm_gate.wait(2)
            return None if self.fault=='drop_arm' else bad if self.fault=='reject_executed_arm' else ok
        if name=='FORCE':
            if self.phase!='armed' or self.active[3] or self.polls<2:return bad
            self.phase='done';return ok
        if name=='ABORT':
            if self.fault=='abort_race':self.phase='done';return bad
            self.phase='ready';return ok
        if name=='RELEASE':self.phase='ready';return ok
        if name in ('CLEAR_EVENTS','FINIT'):return ok
        if name=='GET':
            if self.phase!='done':return bad
            self.get_active.set()
            try:
                n=self.active[1]*100000 if self.active[0]==0 else self.active[1]
                if self.fault=='stall_get':
                    while not self.stop_event.wait(.02):
                        if select.select([conn],[],[],0)[0]:
                            extra=conn.recv(1024)
                            if extra:self.interleaved.append(extra)
                            else:return None
                    return None
                if self.fault=='error_get':return b'08000ABC\r\n?'
                pair=b'08000ABC' if self.fault!='invalid_adc' else b'0800FFFF'
                chunk=pair*min(n,8192);left=n*8
                while left:
                    data=chunk[:left];self._send(conn,data);left-=len(data)
                    if self.mbps:time.sleep(len(data)/(self.mbps*1e6))
                    if select.select([conn],[],[],0)[0]:
                        extra=conn.recv(1024)
                        if not extra:return None
                        self.interleaved.append(extra)
                self.phase='ready'
                if self.active[3]:self.gap_until=time.monotonic()+self.config[9]/1000
                return ok
            finally:self.get_active.clear()
        return bad

    def _serve(self):
        while not self.stop_event.is_set():
            try:conn,_=self.listener.accept()
            except socket.timeout:continue
            except OSError:return
            self.conn=conn
            try:
                with conn:
                    conn.settimeout(.2);buffer=b''
                    while not self.stop_event.is_set():
                        try:data=conn.recv(4096)
                        except socket.timeout:continue
                        if not data:break
                        buffer+=data
                        while b'\r' in buffer:
                            line,buffer=buffer.split(b'\r',1)
                            response=self._handle(conn,line.decode('ascii').strip())
                            if response is not None:self._send(conn,response)
            except (ConnectionError,OSError):pass
            except Exception as exc:self.error=exc
            finally:self.conn=None


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=11235);p.add_argument('--mbps',type=float,default=6)
    args=p.parse_args();server=Simulator(args.port,mbps=args.mbps)
    print(f'V26 simulated device: 127.0.0.1:{server.port}; Ctrl+C to stop')
    try:
        while True:time.sleep(1)
    except KeyboardInterrupt:server.close()
