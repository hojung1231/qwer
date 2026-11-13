"""Scrolling pitch-lane video: the extracted melody as bars, the vocal's measured pitch drawn live.

    python3 render_video.py <out_dir> "<title>" <out.mp4> [start_seconds]

<out_dir> is a vocal2midi output folder; it also needs overlay.wav (the audio track to use).
"""
import sys, json, subprocess, numpy as np, mido
from PIL import Image, ImageDraw, ImageFont
import os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import notes as N
d, title, out = sys.argv[1], sys.argv[2], sys.argv[3]
t_from = float(sys.argv[4]) if len(sys.argv)>4 else None
W,H,FPS,SPAN,NOWX = 1280,720,30,8.0,0.36
BG=(14,18,24); LANE=(20,26,36); GRID=(38,47,62); INK=(238,242,247); MUTED=(140,152,170)
TARGET=(84,98,120); HIT=(53,201,143); MISS=(255,107,97); TRACE=(255,214,102); NOW=(126,162,255)
TOL=0.5; FLAT=0.8      # singers land below the note far more often than above it
rep=json.load(open(d+'/report.json')); org=rep['midi_origin_s']
z=np.load(d+'/f0.npz'); f0,per,rms=z['f0'],z['per'],z['rms']
v=N.voicing(per,rms,rel_db=-18); m=np.where(v,N.hz_to_midi_f(f0),np.nan)      # 10 ms hop, audio time
ns=[]; t=0; on={}
for msg in mido.MidiFile(d+'/melody_quantised.mid'):
    t+=msg.time
    if msg.type=='note_on' and msg.velocity>0: on[msg.note]=t
    elif hasattr(msg,'note') and msg.note in on: a=on.pop(msg.note); ns.append((a+org,t-a,msg.note))
ns=np.array(sorted(ns))
# per-frame target and hit (for colouring), per-note hit ratio
tt=np.arange(len(m))*0.01; idx=np.searchsorted(ns[:,0],tt,side='right')-1; ok=idx>=0; idc=np.clip(idx,0,len(ns)-1)
active=ok&(tt<ns[idc,0]+ns[idc,1]); diff=m-ns[idc,2]
# the tracker sometimes reports a loud held note one octave off; show it where it was sung
oct_err=active&(np.abs(diff)>=9)&(np.abs(diff-12*np.round(diff/12))<3)
m=np.where(oct_err,m-12*np.round(diff/12),m); diff=m-ns[idc,2]
hit=active&(diff<=TOL)&(diff>=-FLAT); sung=active&~np.isnan(m)
cs_hit=np.cumsum(hit); cs_sung=np.cumsum(sung)
note_ok=np.array([ (hit[int(a*100):int((a+l)*100)].sum() >= 0.5*max(1,sung[int(a*100):int((a+l)*100)].sum())) and sung[int(a*100):int((a+l)*100)].sum()>=0.3*max(1,int(l*100)) for a,l,p in ns])
lo,hi=ns[:,2].min()-4,ns[:,2].max()+4
start=(ns[0,0]-3) if t_from is None else t_from; end=min(len(m)*0.01, ns[-1,0]+ns[-1,1]+2)
top,bot,left=96,H-40,70
y=lambda p: top+(bot-top)*(1-(p-lo)/(hi-lo)); pps=(W-left)/SPAN; x0=left+(W-left)*NOWX
F=lambda s: ImageFont.truetype('/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',s); f_t,f_s,f_b=F(30),F(18),F(44)
NAMES=['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
audio=d+'/overlay.wav'
ff=subprocess.Popen(['ffmpeg','-loglevel','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(FPS),'-i','-',
    '-ss',str(start),'-i',audio,'-c:v','libx264','-preset','veryfast','-crf','23','-pix_fmt','yuv420p','-c:a','aac','-b:a','160k','-shortest','-movflags','+faststart',out],stdin=subprocess.PIPE)
base=Image.new('RGB',(W,H),BG); db=ImageDraw.Draw(base); db.rectangle([left,top,W,bot],fill=LANE)
for p in range(int(np.ceil(lo)),int(hi)+1):
    nat=NAMES[p%12][-1]!='#'; 
    if nat: db.line([left,y(p),W,y(p)],fill=GRID,width=1); db.text((left-10,y(p)),NAMES[p%12]+str(p//12-1),font=f_s,fill=MUTED,anchor='rm')
db.text((left,26),title,font=f_t,fill=INK); db.text((left,66),'회색 막대: 추출한 멜로디(목표 음)   노란 선: 육성의 실제 음높이   지나간 막대: 맞으면 초록, 어긋나면 빨강',font=f_s,fill=MUTED)
nh=max(8,(bot-top)/(hi-lo)*0.8)
n_frames=int((end-start)*FPS)
for k in range(n_frames):
    t=start+k/FPS; im=base.copy(); dr=ImageDraw.Draw(im)
    a=np.searchsorted(ns[:,0]+ns[:,1],t-SPAN*NOWX-0.5); b=np.searchsorted(ns[:,0],t+SPAN*(1-NOWX)+0.5)
    for i in range(a,b):
        s,l,p=ns[i]; xa=max(left,x0+(s-t)*pps); xb=min(W,x0+(s+l-t)*pps-2)
        if xb<=xa: continue
        col=TARGET if s+l>t else (HIT if note_ok[i] else MISS)
        if s<=t<s+l: col=(150,165,190)
        dr.rounded_rectangle([xa,y(p)-nh/2,xb,y(p)+nh/2],radius=4,fill=col)
    i0=max(0,int((t-SPAN*NOWX)*100)); i1=min(len(m),int(t*100)+1)
    pts=[]; 
    for j in range(i0,i1):
        if np.isnan(m[j]) or not(lo<=m[j]<=hi):
            if len(pts)>1: dr.line(pts,fill=TRACE,width=3)
            pts=[]; continue
        pts.append((x0+(j*0.01-t)*pps,y(m[j])))
    if len(pts)>1: dr.line(pts,fill=TRACE,width=3)
    if pts: px,py=pts[-1]; dr.ellipse([px-7,py-7,px+7,py+7],fill=TRACE,outline=BG,width=2)
    dr.line([x0,top-8,x0,bot],fill=NOW,width=3)
    j=min(len(m)-1,int(t*100)); sg=cs_sung[j]; acc='%d%%'%round(100*cs_hit[j]/sg) if sg>50 else '–'
    dr.text((W-24,22),acc,font=f_b,fill=INK,anchor='ra'); dr.text((W-24,72),'음정 일치',font=f_s,fill=MUTED,anchor='ra')
    if active[j]:
        tp=int(ns[idc[j],2]); lab=NAMES[tp%12]+str(tp//12-1)
        if not np.isnan(m[j]):
            dd=m[j]-tp; lab+='   %+.0f센트'%(100*dd); colr=HIT if -FLAT<=dd<=TOL else MISS
        else: colr=MUTED
        dr.text((x0+14,top+8),lab,font=f_s,fill=colr)
    dr.text((W-24,bot+8),'%d:%02d'%(t//60,t%60),font=f_s,fill=MUTED,anchor='ra')
    ff.stdin.write(im.tobytes())
ff.stdin.close(); ff.wait(); print(out,n_frames,'frames, final acc',acc)
