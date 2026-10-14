"""One background reader/reducer with latest-only requests and results."""
import threading
from ..models.recording import load_recording,make_view,ParseCancelled


class WaveformWorker:
    def __init__(self):
        self.condition=threading.Condition();self.pending=None;self.result=None;self.progress=(0,0)
        self.cancel=threading.Event();self.stopped=False;self.generation=0
        self.thread=threading.Thread(target=self.run,name='waveform-reader',daemon=True);self.thread.start()

    def request(self,kind,*args):
        with self.condition:
            if self.stopped:return None
            self.generation+=1;self.cancel.set();self.cancel=threading.Event()
            self.pending=(self.generation,kind,args,self.cancel);self.result=None;self.progress=(0,0)
            self.condition.notify();return self.generation

    def poll(self):
        with self.condition:
            result=self.result;self.result=None;return result,self.progress

    def close(self):
        with self.condition:
            self.stopped=True;self.cancel.set();self.pending=None;self.result=None;self.condition.notify()

    def run(self):
        while True:
            with self.condition:
                self.condition.wait_for(lambda:self.stopped or self.pending is not None)
                if self.stopped:return
                generation,kind,args,cancel=self.pending;self.pending=None
            def progress(done,total):
                with self.condition:
                    if generation==self.generation:self.progress=(done,total)
            try:
                if kind=='load':
                    record=load_recording(args[0],cancel=cancel,progress=progress)
                    if cancel.is_set():raise ParseCancelled()
                    value=(record,make_view(record))
                else:value=make_view(args[0],start=args[1],stop=args[2])
                result=(generation,kind,value,None)
            except Exception as exc:result=(generation,kind,None,exc)
            with self.condition:
                if not self.stopped and not cancel.is_set() and generation==self.generation:self.result=result
            # Drop references to potentially large arrays before waiting again.
            args=result=value=record=None
