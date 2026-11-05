import type {Annotation} from './model';
export const THUMB_WIDTH=60,THUMB_STEP=42;
export const renumber=(shapes:Annotation[])=>shapes.map((shape,index)=>({...shape,number:index+1}));
export type TouchPoint={id:number;x:number;y:number};
export type TwoPointState={ids:[number,number]|null;firstId?:number;finished:boolean};
export function resizeFromTouches(shape:Annotation,touches:TouchPoint[],state:TwoPointState):Annotation{
 if(state.finished)return shape;
 if(!state.ids&&touches.length>=2){const first=touches.find(t=>t.id===state.firstId)||touches[0];state.ids=[first.id,touches.find(t=>t.id!==first.id)!.id];}
 if(!state.ids)return shape;
 const a=touches.find(t=>t.id===state.ids![0]),b=touches.find(t=>t.id===state.ids![1]);
 if(!a||!b){state.finished=true;return shape;}
 return {...shape,x1:a.x,y1:a.y,x2:b.x,y2:b.y};
}
export const clamp=(v:number,min=0,max=1)=>Math.max(min,Math.min(max,v));
export function hitShape(shapes:Annotation[],x:number,y:number,width:number,height:number){return [...shapes].reverse().find(shape=>{const a={x:shape.x1*width,y:shape.y1*height},b={x:shape.x2*width,y:shape.y2*height},p={x:x*width,y:y*height};if(shape.kind==='arrow'){const dx=b.x-a.x,dy=b.y-a.y,t=clamp(((p.x-a.x)*dx+(p.y-a.y)*dy)/(dx*dx+dy*dy||1));return Math.hypot(p.x-a.x-t*dx,p.y-a.y-t*dy)<24;}const left=Math.min(a.x,b.x)-15,right=Math.max(a.x,b.x)+15,top=Math.min(a.y,b.y)-15,bottom=Math.max(a.y,b.y)+15;return p.x>=left&&p.x<=right&&p.y>=top&&p.y<=bottom;});}
export function translateShape(s:Annotation,dx:number,dy:number){const x=clamp(dx,-Math.min(s.x1,s.x2),1-Math.max(s.x1,s.x2)),y=clamp(dy,-Math.min(s.y1,s.y2),1-Math.max(s.y1,s.y2));return {...s,x1:s.x1+x,x2:s.x2+x,y1:s.y1+y,y2:s.y2+y};}
