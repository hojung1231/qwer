// Pitch tracks of each vocal at 30 fps for several YIN thresholds / gates (mirrors the page's detector).
const fs=require('fs'); const sr=48000, N=2048, W=N>>1, FPS=30;
const THR=[0.10,0.15,0.20,0.30], GATE=[0.004,0.008,0.016];
for(const d of ['out3','out2','out_demucs']){
  const b=fs.readFileSync(d+'.f32'); const x=new Float32Array(b.buffer,b.byteOffset,b.length/4);
  const nf=Math.floor(x.length/sr*FPS); const out={fps:FPS,rms:[],f:THR.map(()=>[])};
  const tmin=Math.floor(sr/1100), tmax=Math.min(W-1,Math.floor(sr/65)), dd=new Float32Array(tmax+2);
  for(let k=0;k<nf;k++){
    const e=Math.floor(k/FPS*sr), s=e-N; if(s<0){out.rms.push(0);out.f.forEach(a=>a.push(0));continue}
    let rms=0; for(let i=0;i<W;i++) rms+=x[s+i]*x[s+i]; rms=Math.sqrt(rms/W); out.rms.push(+rms.toFixed(5));
    if(rms<GATE[0]){out.f.forEach(a=>a.push(0));continue}
    let run=0; for(let tau=1;tau<=tmax+1;tau++){let q=0;for(let i=0;i<W;i++){const v=x[s+i]-x[s+i+tau];q+=v*v} run+=q; dd[tau]=run>0?q*tau/run:1}
    THR.forEach((th,ti)=>{ let best=-1; for(let tau=Math.max(2,tmin);tau<=tmax;tau++){ if(dd[tau]<th){ while(tau+1<=tmax&&dd[tau+1]<dd[tau]) tau++; best=tau; break } }
      if(best<0){out.f[ti].push(0);return} const a=dd[best-1],b2=dd[best],c=dd[best+1],sh=(a+c-2*b2)!==0?0.5*(a-c)/(a+c-2*b2):0; out.f[ti].push(+(sr/(best+sh)).toFixed(2)) });
  }
  fs.writeFileSync(d+'.track.json',JSON.stringify({THR,GATE,...out})); console.log(d,nf,'frames');
}
