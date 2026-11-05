package com.bogo.touch;

import android.app.Activity;
import android.content.Intent;
import android.graphics.BitmapFactory;
import android.net.Uri;
import android.os.Bundle;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.security.MessageDigest;
import org.json.JSONObject;

/** Test-only local receiver: verifies the share payload without sending it to a service. */
public class ShareReceiver extends Activity {
  @Override public void onCreate(Bundle bundle){
    super.onCreate(bundle);
    JSONObject result=new JSONObject();
    try {
      Intent intent=getIntent();Uri uri=intent.getParcelableExtra(Intent.EXTRA_STREAM);
      result.put("action",intent.getAction());result.put("mime",intent.getType());result.put("hasText",intent.hasExtra(Intent.EXTRA_TEXT));
      if(uri==null){result.put("text",intent.getStringExtra(Intent.EXTRA_TEXT));result.put("count",0);}else{
      MessageDigest digest=MessageDigest.getInstance("SHA-256");byte[] buffer=new byte[65536];
      try(InputStream input=getContentResolver().openInputStream(uri)){int read;while((read=input.read(buffer))!=-1)digest.update(buffer,0,read);}
      StringBuilder sha=new StringBuilder();for(byte b:digest.digest())sha.append(String.format("%02x",b&255));
      BitmapFactory.Options options=new BitmapFactory.Options();options.inJustDecodeBounds=true;
      try(InputStream input=getContentResolver().openInputStream(uri)){BitmapFactory.decodeStream(input,null,options);}
      result.put("action",intent.getAction());result.put("mime",intent.getType());result.put("sha256",sha.toString());
      result.put("width",options.outWidth);result.put("height",options.outHeight);
      result.put("count",intent.getClipData()==null?1:intent.getClipData().getItemCount());
      result.put("hasText",intent.hasExtra(Intent.EXTRA_TEXT));
      result.put("hasMultipleStreams",intent.getExtras().get(Intent.EXTRA_STREAM) instanceof java.util.ArrayList);
      }
    }catch(Throwable error){try{result.put("error",error.toString());}catch(Exception ignored){}}
    try(FileOutputStream output=new FileOutputStream(new File(getFilesDir(),"share-result.json"))){output.write(result.toString().getBytes("UTF-8"));}catch(Exception ignored){}
    finish();
  }
}
