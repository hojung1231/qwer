import type {Annotation} from './model';
export const THUMB_WIDTH=60,THUMB_STEP=42;
export const renumber=(shapes:Annotation[])=>shapes.map((shape,index)=>({...shape,number:index+1}));
export type TouchPoint={id:number;x:number;y:number};
export type PinchAxis='both'|'horizontal'|'vertical';
export type TwoPointState={ids:[number,number]|null;firstId?:number;finished:boolean;baseline?:{shape:Annotation;distance:number;gapX:number;gapY:number;midX:number;midY:number;axis:PinchAxis}};
export function pinchAxis(shape:Annotation,a:TouchPoint,b:TouchPoint):PinchAxis{
 const region=(value:number,start:number,end:number)=>value<Math.min(start,end)?-1:value>Math.max(start,end)?1:0;
 const ax=region(a.x,shape.x1,shape.x2),bx=region(b.x,shape.x1,shape.x2),ay=region(a.y,shape.y1,shape.y2),by=region(b.y,shape.y1,shape.y2);
 if(ay*by===-1&&ax===bx)return 'vertical';
 if(ax*bx===-1&&ay===by)return 'horizontal';
 return 'both';
}
// Existing objects retain their original geometry when the second finger lands.
// A wide grip naturally produces a smaller scale change for the same travel.
export function pinchFromTouches(shape:Annotation,touches:TouchPoint[],state:TwoPointState,width:number,height:number):Annotation{
 if(state.finished)return shape;
 if(!state.ids&&touches.length>=2)state.ids=[touches[0].id,touches[1].id];
 if(!state.ids)return shape;
 const a=touches.find(t=>t.id===state.ids![0]),b=touches.find(t=>t.id===state.ids![1]);
 if(!a||!b){state.finished=true;return shape;}
 const distance=Math.hypot((b.x-a.x)*width,(b.y-a.y)*height),midX=(a.x+b.x)/2,midY=(a.y+b.y)/2;
 if(!state.baseline){state.baseline={shape:{...shape},distance:Math.max(1,distance),gapX:Math.abs(b.x-a.x),gapY:Math.abs(b.y-a.y),midX,midY,axis:pinchAxis(shape,a,b)};return shape;}
 const initial=state.baseline,s=initial.shape,w=Math.abs(s.x2-s.x1),h=Math.abs(s.y2-s.y1);
 const scale=Math.min(Math.max(.02,distance/initial.distance),w?1/w:Infinity,h?1/h:Infinity);
 // Lock the axis from the starting regions for the entire gesture.
 const scaleX=initial.axis==='vertical'?1:initial.axis==='horizontal'?Math.min(Math.max(.02,Math.abs(b.x-a.x)/initial.gapX),w?1/w:Infinity):scale;
 const scaleY=initial.axis==='horizontal'?1:initial.axis==='vertical'?Math.min(Math.max(.02,Math.abs(b.y-a.y)/initial.gapY),h?1/h:Infinity):scale;
 const halfW=w*scaleX/2,halfH=h*scaleY/2;
 const cx=clamp((s.x1+s.x2)/2+midX-initial.midX,halfW,1-halfW),cy=clamp((s.y1+s.y2)/2+midY-initial.midY,halfH,1-halfH);
 return {...s,x1:cx+(s.x1-s.x2)*scaleX/2,y1:cy+(s.y1-s.y2)*scaleY/2,x2:cx+(s.x2-s.x1)*scaleX/2,y2:cy+(s.y2-s.y1)*scaleY/2};
}
export function movedPastHold(start:{x:number;y:number},point:{x:number;y:number},width:number,height:number){return Math.hypot((point.x-start.x)*width,(point.y-start.y)*height)>8;}
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

export function centeredCrop(width:number,height:number,ratio:number){
 const cropWidth=width/height>ratio?Math.round(height*ratio):width;
 const cropHeight=width/height>ratio?height:Math.round(width/ratio);
 return {originX:Math.floor((width-cropWidth)/2),originY:Math.floor((height-cropHeight)/2),width:cropWidth,height:cropHeight};
}
