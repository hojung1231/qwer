import json, itertools, numpy as np
from scipy.ndimage import median_filter
SONGS=['out3','out2','out_demucs']; T={}
for d in SONGS:
    tr=json.load(open(d+'.track.json')); ns=np.array(json.load(open(d+'.notes.json')))
    T[d]=dict(f=[np.array(a) for a in tr['f']],rms=np.array(tr['rms']),fps=tr['fps'],ns=ns,THR=tr['THR'])
import functools
@functools.lru_cache(None)
def sung_track(d,ti,gate,med):
    s=T[d]; f=s['f'][ti].copy(); f[s['rms']<gate]=0
    m=np.where(f>0,69+12*np.log2(np.maximum(f,1)/440),np.nan)
    if med>1:   # page: median of last `med` frames, needs >=2 valid
        out=np.full(len(m),np.nan)
        for k in range(len(m)):
            v=m[max(0,k-med+1):k+1]; v=v[~np.isnan(v)]
            if len(v)>=min(2,med): out[k]=np.sort(v)[len(v)//2]
        m=out
    return m
def judge(d,m,lat,tol,grace=0.0,shift=0.0,tshift=0.0):
    s=T[d]; ns=s['ns']; t=np.arange(len(m))/s['fps']-lat-tshift
    idx=np.searchsorted(ns[:,0],t,side='right')-1
    ok=(idx>=0); idx=np.clip(idx,0,len(ns)-1); active=ok&(t<ns[idx,0]+ns[idx,1])
    tp=ns[idx,2]+shift; diff=m-tp; diff=diff-12*np.round(diff/12); hit=np.abs(diff)<=tol
    if grace>0:   # near a note edge the neighbouring note's pitch is accepted too
        for nb,edge in ((idx-1,t-ns[idx,0]),(idx+1,ns[idx,0]+ns[idx,1]-t)):
            nbc=np.clip(nb,0,len(ns)-1); d2=m-(ns[nbc,2]+shift); d2=d2-12*np.round(d2/12)
            hit|=(edge<grace)&(np.abs(d2)<=tol)&(nb>=0)&(nb<len(ns))
    sung=active&~np.isnan(m)
    return (hit&sung).sum()/max(1,sung.sum()), sung.sum()/max(1,active.sum())
@functools.lru_cache(None)
def one(c,d):
    ti,gate,med,lat,tol,grace=c; m=sung_track(d,ti,gate,med); a,cv=judge(d,m,lat,tol,grace)
    return (a,max(judge(d,m,lat,tol,grace,shift=x)[0] for x in (1,-1)),max(judge(d,m,lat,tol,grace,shift=x)[0] for x in (2,-2)),judge(d,m,lat,tol,grace,tshift=20)[0],cv)
def evalcfg(c,songs=SONGS):
    v=np.mean([one(tuple(c),d) for d in songs],axis=0)
    return dict(zip(('pos','semi','tone','time','cov'),map(float,v)))
def obj(r): return r['pos']-r['semi']+0.3*r['cov']
if __name__=='__main__':
    cur=(1,0.008,3,0.12,0.7,0.0); print('current page  ',cur,{k:round(v,3) for k,v in evalcfg(cur).items()})
    cache={}
    grid=list(itertools.product(range(4),(0.004,0.008,0.016),(1,3,5),(0.0,0.03,0.06,0.09,0.12,0.16),(0.4,0.5,0.6,0.7,0.8),(0.0,0.06,0.10)))
    import time; t0=time.time()
    res=[(obj(r),c,r) for c in grid for r in [evalcfg(c)]]
    res.sort(key=lambda x:-x[0]); print('searched',len(grid),'in %.0fs'%(time.time()-t0))
    for o,c,r in res[:6]: print('best',c,{k:round(v,3) for k,v in r.items()},'obj %.3f'%o)
    # leave-one-song-out: choose on two songs, test on the third
    for held in SONGS:
        tr=[s for s in SONGS if s!=held]
        b=max(grid,key=lambda c:obj(evalcfg(c,tr)))
        print('held-out',held,'chosen',b,'->',{k:round(v,3) for k,v in evalcfg(b,[held]).items()},'| current:',{k:round(v,3) for k,v in evalcfg(cur,[held]).items()})
    json.dump(res[0][1],open('best.json','w'))
