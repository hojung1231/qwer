package com.bogo.touch;

import android.app.Instrumentation;
import android.app.Activity;
import android.os.Bundle;
import android.os.SystemClock;
import android.view.InputDevice;
import android.view.MotionEvent;
import android.view.accessibility.AccessibilityNodeInfo;
import android.graphics.Bitmap;
import android.graphics.Rect;

/** Test-only APK: inject real multitouch through UiAutomation into the running app. */
public class Touch extends Instrumentation {
  Bundle args;long down;
  @Override public void onCreate(Bundle bundle){super.onCreate(bundle);args=bundle;start();}
  void event(int action,float[][] points)throws Exception{
    MotionEvent.PointerProperties[] properties=new MotionEvent.PointerProperties[points.length];
    MotionEvent.PointerCoords[] coords=new MotionEvent.PointerCoords[points.length];
    for(int i=0;i<points.length;i++){
      properties[i]=new MotionEvent.PointerProperties();properties[i].id=i;properties[i].toolType=MotionEvent.TOOL_TYPE_FINGER;
      coords[i]=new MotionEvent.PointerCoords();coords[i].x=points[i][0];coords[i].y=points[i][1];coords[i].pressure=1;coords[i].size=1;
    }
    MotionEvent event=MotionEvent.obtain(down,SystemClock.uptimeMillis(),action,points.length,properties,coords,0,0,1,1,0,0,InputDevice.SOURCE_TOUCHSCREEN,0);
    if(!getUiAutomation().injectInputEvent(event,true))throw new Exception("Touch injection rejected");
    event.recycle();Thread.sleep(80);
  }
  float number(String key){return Float.parseFloat(args.getString(key));}
  Rect trash(AccessibilityNodeInfo node){
    if(node==null)return null;
    if(node.getText()!=null&&node.getText().toString().contains("여기로 끌어 삭제")){Rect r=new Rect();node.getBoundsInScreen(r);return r;}
    for(int i=0;i<node.getChildCount();i++){Rect r=trash(node.getChild(i));if(r!=null)return r;}
    return null;
  }
  @Override public void onStart(){
    Bundle result=new Bundle();
    try {
      down=SystemClock.uptimeMillis();float x=number("x1"),y=number("y1"),x2=number("x2"),y2=number("y2");
      event(MotionEvent.ACTION_DOWN,new float[][]{{x,y}});
      if("delete".equals(args.getString("mode"))){
        Thread.sleep(650);Rect target=trash(getUiAutomation().getRootInActiveWindow());
        if(target==null)throw new Exception("Trash target missing");
        event(MotionEvent.ACTION_MOVE,new float[][]{{target.exactCenterX(),target.exactCenterY()}});
        event(MotionEvent.ACTION_UP,new float[][]{{target.exactCenterX(),target.exactCenterY()}});
        result.putString("deleted","true");
      }else{
        event(MotionEvent.ACTION_POINTER_DOWN|(1<<MotionEvent.ACTION_POINTER_INDEX_SHIFT),new float[][]{{x,y},{x2,y2}});
        event(MotionEvent.ACTION_MOVE,new float[][]{{x+12,y+12},{x2-12,y2-12}});Thread.sleep(200);
        Bitmap before=getUiAutomation().takeScreenshot();
        event(MotionEvent.ACTION_POINTER_UP|(1<<MotionEvent.ACTION_POINTER_INDEX_SHIFT),new float[][]{{x+12,y+12},{x2-12,y2-12}});
        event(MotionEvent.ACTION_MOVE,new float[][]{{(x+x2)/2,(y+y2)/2}});
        event(MotionEvent.ACTION_UP,new float[][]{{(x+x2)/2,(y+y2)/2}});Thread.sleep(250);
        Bitmap after=getUiAutomation().takeScreenshot();
        int left=(int)number("left"),top=(int)number("top"),width=(int)number("width"),height=(int)number("height");
        Bitmap a=Bitmap.createBitmap(before,left,top,width,height),b=Bitmap.createBitmap(after,left,top,width,height);
        if(!a.sameAs(b))throw new Exception("Shape pixels changed after one finger lifted");
        result.putString("stable","true");a.recycle();b.recycle();before.recycle();after.recycle();
      }
      finish(Activity.RESULT_OK,result);
    }catch(Throwable error){result.putString("error",error.toString());finish(Activity.RESULT_CANCELED,result);}
  }
}
