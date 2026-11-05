package com.bogo.touch;

import android.app.Instrumentation;
import android.app.Activity;
import android.os.Bundle;
import android.os.SystemClock;
import android.view.InputDevice;
import android.view.MotionEvent;
import android.view.accessibility.AccessibilityNodeInfo;
import android.graphics.Bitmap;
import android.graphics.Color;
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
  Bitmap canvasShot(){Bitmap full=getUiAutomation().takeScreenshot();Bitmap crop=Bitmap.createBitmap(full,(int)number("left"),(int)number("top"),(int)number("width"),(int)number("height"));full.recycle();return crop;}
  Rect redBounds(Bitmap image){
    int w=image.getWidth(),h=image.getHeight(),left=w,right=-1,top=h,bottom=-1;int[] pixels=new int[w*h];image.getPixels(pixels,0,w,0,0,w,h);
    for(int i=0;i<pixels.length;i++)if(Color.red(pixels[i])>180&&Color.green(pixels[i])<130&&Color.blue(pixels[i])<130){left=Math.min(left,i%w);right=Math.max(right,i%w);top=Math.min(top,i/w);bottom=Math.max(bottom,i/w);}
    if(right<left)throw new IllegalStateException("Shape not visible");return new Rect(left,top,right+1,bottom+1);
  }
  int redWidth(Bitmap image){return redBounds(image).width();}
  Rect trash(AccessibilityNodeInfo node){
    if(node==null)return null;
    if(node.getText()!=null&&node.getText().toString().contains("여기로 끌어 삭제")){Rect r=new Rect();node.getBoundsInScreen(r);return r;}
    for(int i=0;i<node.getChildCount();i++){Rect r=trash(node.getChild(i));if(r!=null)return r;}
    return null;
  }
  AccessibilityNodeInfo labelled(AccessibilityNodeInfo node,String label){
    if(node==null)return null;
    if(label.contentEquals(node.getContentDescription()==null?"":node.getContentDescription()))return node;
    for(int i=0;i<node.getChildCount();i++){AccessibilityNodeInfo found=labelled(node.getChild(i),label);if(found!=null)return found;}
    return null;
  }
  Rect titleBounds()throws Exception{
    for(int retry=0;retry<20;retry++){
      AccessibilityNodeInfo node=labelled(getUiAutomation().getRootInActiveWindow(),"작업 제목");
      if(node!=null){Rect bounds=new Rect();node.getBoundsInScreen(bounds);return bounds;}
      Thread.sleep(100);
    }
    throw new Exception("Work title disappeared during strip drag");
  }
  void selected(int number)throws Exception{
    AccessibilityNodeInfo node=labelled(getUiAutomation().getRootInActiveWindow(),"현장 기록 "+number+" 선택");
    if(node==null||!node.isSelected())throw new Exception("Drag stopped before record "+number);
  }
  @Override public void onStart(){
    Bundle result=new Bundle();
    try {
      down=SystemClock.uptimeMillis();float x=number("x1"),y=number("y1"),x2=number("x2"),y2=number("y2");
      String mode=args.getString("mode");
      event(MotionEvent.ACTION_DOWN,new float[][]{{x,y}});
      Rect title=mode.startsWith("strip")||mode.startsWith("project")?titleBounds():null;
      if(mode.startsWith("project")){
        Thread.sleep(180);
        for(int i=1;i<=12;i++){
          event(MotionEvent.ACTION_MOVE,new float[][]{{x+(x2-x)*i/12f,y+(y2-y)*i/12f}});
          if(!title.equals(titleBounds()))throw new Exception("Project wheel scrolled the whole page");
        }
        event(MotionEvent.ACTION_UP,new float[][]{{x2,y2}});Thread.sleep(650);
        if(!title.equals(titleBounds()))throw new Exception("Page moved when project wheel stopped");
        result.putString("projectStable","true");
      }else if(mode.startsWith("strip")){
        Thread.sleep(450);selected(1);
        for(int leg=0;leg<3;leg++){
          float from=leg%2==0?x:x2,to=leg%2==0?x2:x;
          for(int i=1;i<=12;i++){
            float nextX=from+(to-from)*i/12f,nextY=y+(i%2==0?40:-40);
            event(MotionEvent.ACTION_MOVE,new float[][]{{nextX,nextY}});
            if(!title.equals(titleBounds()))throw new Exception("Vertical page scroll intercepted thumbnail drag");
          }
          selected(leg%2==0?2:1);
        }
        event(mode.equals("strip-cancel")?MotionEvent.ACTION_CANCEL:MotionEvent.ACTION_UP,new float[][]{{x2,y+40}});
        Thread.sleep(250);
        if(!title.equals(titleBounds()))throw new Exception("Page moved when thumbnail drag ended");
        result.putString("stripStable","true");
      }else if("move-no-trash".equals(mode)){
        event(MotionEvent.ACTION_MOVE,new float[][]{{x+36,y}});Thread.sleep(650);
        if(trash(getUiAutomation().getRootInActiveWindow())!=null)throw new Exception("Moving object incorrectly opened trash");
        event(MotionEvent.ACTION_UP,new float[][]{{x+36,y}});result.putString("movedWithoutTrash","true");
      }else if(mode.startsWith("axis-")){
        Bitmap original=canvasShot();Rect initial=redBounds(original);
        event(MotionEvent.ACTION_POINTER_DOWN|(1<<MotionEvent.ACTION_POINTER_INDEX_SHIFT),new float[][]{{x,y},{x2,y2}});Thread.sleep(150);
        Bitmap landed=canvasShot();if(!original.sameAs(landed))throw new Exception("Axis resize jumped on touch down");landed.recycle();
        boolean vertical=mode.equals("axis-vertical");float cx=(x+x2)/2,cy=(y+y2)/2;
        for(float factor:new float[]{.75f,1.15f}){
          event(MotionEvent.ACTION_MOVE,new float[][]{{cx+(x-cx)*factor+10,cy+(y-cy)*factor+8},{cx+(x2-cx)*factor+10,cy+(y2-cy)*factor+8}});Thread.sleep(180);
          Bitmap resized=canvasShot();Rect actual=redBounds(resized);
          if(Math.abs(actual.width()-initial.width()*(vertical?1:factor))>12||Math.abs(actual.height()-initial.height()*(vertical?factor:1))>18)throw new Exception("Incorrect independent axis dimensions: "+mode+" "+initial+" -> "+actual);
          if(Math.abs(actual.exactCenterX()-initial.exactCenterX()-10)>5||Math.abs(actual.exactCenterY()-initial.exactCenterY()-8)>5)throw new Exception("Axis pinch did not pan with both fingers");resized.recycle();
        }
        Bitmap before=canvasShot();
        event(MotionEvent.ACTION_POINTER_UP|(1<<MotionEvent.ACTION_POINTER_INDEX_SHIFT),new float[][]{{cx+(x-cx)*1.15f+10,cy+(y-cy)*1.15f+8},{cx+(x2-cx)*1.15f+10,cy+(y2-cy)*1.15f+8}});
        event(MotionEvent.ACTION_MOVE,new float[][]{{cx,cy}});event(MotionEvent.ACTION_UP,new float[][]{{cx,cy}});Thread.sleep(200);
        Bitmap after=canvasShot();if(!before.sameAs(after))throw new Exception("Axis shape changed on finger release");
        before.recycle();after.recycle();original.recycle();result.putString("axisStable","true");
      }else if(mode.startsWith("pinch")){
        Bitmap original=canvasShot();int initialWidth=redWidth(original);
        event(MotionEvent.ACTION_POINTER_DOWN|(1<<MotionEvent.ACTION_POINTER_INDEX_SHIFT),new float[][]{{x,y},{x2,y2}});Thread.sleep(150);
        Bitmap landed=canvasShot();if(!original.sameAs(landed))throw new Exception("Existing shape jumped when fingers landed");landed.recycle();
        float cx=(x+x2)/2,cy=(y+y2)/2;
        for(float factor:new float[]{.7f,1.2f}){
          event(MotionEvent.ACTION_MOVE,new float[][]{{cx+(x-cx)*factor,cy+(y-cy)*factor},{cx+(x2-cx)*factor,cy+(y2-cy)*factor}});Thread.sleep(180);
          Bitmap resized=canvasShot();if(Math.abs(redWidth(resized)-initialWidth*factor)>12)throw new Exception("Pinch did not follow relative finger spacing: "+factor);resized.recycle();
        }
        Bitmap before=canvasShot();
        event(MotionEvent.ACTION_POINTER_UP|(1<<MotionEvent.ACTION_POINTER_INDEX_SHIFT),new float[][]{{cx+(x-cx)*1.2f,cy+(y-cy)*1.2f},{cx+(x2-cx)*1.2f,cy+(y2-cy)*1.2f}});
        event(MotionEvent.ACTION_MOVE,new float[][]{{cx,cy}});event(MotionEvent.ACTION_UP,new float[][]{{cx,cy}});Thread.sleep(200);
        Bitmap after=canvasShot();if(!before.sameAs(after))throw new Exception("Pinched shape changed when one finger lifted");
        before.recycle();after.recycle();original.recycle();result.putString("pinchStable","true");
      }else if("delete".equals(mode)){
        Thread.sleep(650);Rect target=trash(getUiAutomation().getRootInActiveWindow());
        if(target==null)throw new Exception("Trash target missing");
        Bitmap screen=getUiAutomation().takeScreenshot();if(target.centerX()<screen.getWidth()*.7||target.centerY()<screen.getHeight()*.6)throw new Exception("Trash is not at bottom right");screen.recycle();
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
        if("resize-sized".equals(mode)){
          int min=width,max=-1;int[] pixels=new int[width*height];a.getPixels(pixels,0,width,0,0,width,height);
          for(int i=0;i<pixels.length;i++)if(Color.red(pixels[i])>180&&Color.green(pixels[i])<130&&Color.blue(pixels[i])<130){min=Math.min(min,i%width);max=Math.max(max,i%width);}
          float expected=Math.abs(x2-x)-24;
          if(max<min||Math.abs((max-min+1)-expected)>35)throw new Exception("Selected shape did not resize to the arbitrary touch points");
        }
        result.putString("stable","true");a.recycle();b.recycle();before.recycle();after.recycle();
      }
      finish(Activity.RESULT_OK,result);
    }catch(Throwable error){result.putString("error",error.toString());finish(Activity.RESULT_CANCELED,result);}
  }
}
