import type {Annotation} from './model';
export const THUMB_WIDTH=60,THUMB_STEP=48;
export const clamp=(v:number,min=0,max=1)=>Math.max(min,Math.min(max,v));
export function hitShape(shapes:Annotation[],x:number,y:number,width:number,height:number){return [...shapes].reverse().find(shape=>{const a={x:shape.x1*width,y:shape.y1*height},b={x:shape.x2*width,y:shape.y2*height},p={x:x*width,y:y*height};if(shape.kind==='arrow'){const dx=b.x-a.x,dy=b.y-a.y,t=clamp(((p.x-a.x)*dx+(p.y-a.y)*dy)/(dx*dx+dy*dy||1));return Math.hypot(p.x-a.x-t*dx,p.y-a.y-t*dy)<24;}const left=Math.min(a.x,b.x)-15,right=Math.max(a.x,b.x)+15,top=Math.min(a.y,b.y)-15,bottom=Math.max(a.y,b.y)+15;return p.x>=left&&p.x<=right&&p.y>=top&&p.y<=bottom;});}
export function translateShape(s:Annotation,dx:number,dy:number){const x=clamp(dx,-Math.min(s.x1,s.x2),1-Math.max(s.x1,s.x2)),y=clamp(dy,-Math.min(s.y1,s.y2),1-Math.max(s.y1,s.y2));return {...s,x1:s.x1+x,x2:s.x2+x,y1:s.y1+y,y2:s.y2+y};}
