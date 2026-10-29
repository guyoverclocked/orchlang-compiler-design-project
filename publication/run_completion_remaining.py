"""Finish the frozen campaign with at most three inference workers on this host."""
import ctypes,json,sys,time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from run_completion_queue import ROOT,OUT,run,log
sys.path.insert(0,str(ROOT/'unified-publication'))
from publication.audit_execution import snapshot

class Watch:
    def __init__(self,pid):
        api=ctypes.windll.kernel32
        api.OpenProcess.argtypes=[ctypes.c_ulong,ctypes.c_int,ctypes.c_ulong]
        api.OpenProcess.restype=ctypes.c_void_p
        api.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_ulong]
        api.WaitForSingleObject.restype=ctypes.c_ulong
        api.CloseHandle.argtypes=[ctypes.c_void_p]
        self.api=api;self.handle=api.OpenProcess(0x100000,0,pid)
    def exited(self):return not self.handle or self.api.WaitForSingleObject(self.handle,0)==0
    def close(self):
        if self.handle:self.api.CloseHandle(self.handle)

def wait_complete(group,name,n,watch):
    directory=OUT/group/name
    while True:
        m=json.loads((directory/'run-manifest.json').read_text())
        allowed=set(m['selected_ids']);assert len(allowed)==n
        a,pa=snapshot(directory/'orig.jsonl');b,pb=snapshot(directory/'ours.jsonl')
        if set(a)==set(b)==allowed and not pa and not pb:return
        if watch.exited():raise RuntimeError('worker stopped before complete records: '+group+'/'+name)
        time.sleep(10)

if __name__=='__main__':
    sw,cr=Watch(int(sys.argv[1])),Watch(int(sys.argv[2]))
    try:
        wait_complete('replication','switch',210,sw)
        log(dict(event='existing-leaf-complete-by-record-guard',workflow='switch',group='replication'))
        def corrective():
            wait_complete('main','crag',150,cr)
            return run('crag',150,'replication',True)
        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs=[pool.submit(run,'email',152,'replication',True),pool.submit(corrective)]
            exits=[job.result() for job in jobs]
        log(dict(event='remaining-replication-finished',exits=exits))
        raise SystemExit(int(any(exits)))
    finally:sw.close();cr.close()
