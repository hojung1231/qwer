package com.hojung1231.hwaeumwang;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.Context;
import android.content.pm.PackageManager;
import android.media.AudioManager;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.webkit.JavascriptInterface;
import android.view.WindowManager;
import android.webkit.PermissionRequest;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import androidx.webkit.WebViewAssetLoader;

/**
 * The whole interface is the bundled web page; this activity only gives it what a browser tab
 * would: a secure origin, the microphone, and a file picker.
 */
public class MainActivity extends Activity {
    private static final String START = "https://appassets.androidplatform.net/assets/www/index.html";
    private static final int REQ_FILES = 1, REQ_MIC = 2;

    private WebView web;
    private ValueCallback<Uri[]> fileCallback;
    private PermissionRequest pendingMic;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);   // practising takes minutes without touching the screen
        web = new WebView(this);
        web.setBackgroundColor(0xFF0C0C10);
        setContentView(web);

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);                       // localStorage and IndexedDB keep the library on the device
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(true);

        // Serve the bundled page from an https origin: getUserMedia needs a secure context.
        final WebViewAssetLoader assets = new WebViewAssetLoader.Builder()
                .addPathHandler("/assets/", new WebViewAssetLoader.AssetsPathHandler(this)).build();
        web.setWebViewClient(new WebViewClient() {
            @Override
            public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                return assets.shouldInterceptRequest(request.getUrl());
            }
        });

        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onPermissionRequest(final PermissionRequest request) {
                boolean wantsMic = false;
                for (String r : request.getResources()) if (PermissionRequest.RESOURCE_AUDIO_CAPTURE.equals(r)) wantsMic = true;
                if (!wantsMic) { request.deny(); return; }
                if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
                    request.grant(new String[]{PermissionRequest.RESOURCE_AUDIO_CAPTURE});
                } else {
                    pendingMic = request;
                    requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, REQ_MIC);
                }
            }

            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (fileCallback != null) fileCallback.onReceiveValue(null);
                fileCallback = callback;
                Intent pick = new Intent(Intent.ACTION_OPEN_DOCUMENT);
                pick.addCategory(Intent.CATEGORY_OPENABLE);
                pick.setType("*/*");
                // songs and the harmony data files that go with them
                pick.putExtra(Intent.EXTRA_MIME_TYPES, new String[]{"audio/*", "application/json", "application/octet-stream", "text/plain"});
                pick.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true);
                try {
                    startActivityForResult(pick, REQ_FILES);
                } catch (Exception e) {
                    fileCallback = null;
                    return false;
                }
                return true;
            }
        });

        setVolumeControlStream(AudioManager.STREAM_MUSIC);   // the volume keys always move the music volume
        web.addJavascriptInterface(new Bridge(), "Android");

        if (state == null) web.loadUrl(START); else web.restoreState(state);
    }

    /**
     * Opening the microphone makes the WebView treat the session as a phone call: Android switches
     * to call mode, a Bluetooth headset drops to its low-quality call link and playback follows the
     * (separate, usually low) call volume, so the music turns quiet.  Practising is not a call:
     * put the phone back in normal mode so the song keeps playing as music, in full quality, while
     * the phone's own microphone listens.
     */
    private void keepMusicMode() {
        final AudioManager am = (AudioManager) getSystemService(Context.AUDIO_SERVICE);
        final Handler h = new Handler(Looper.getMainLooper());
        for (long delay : new long[]{0, 300, 1000, 2500, 5000}) {       // the WebView sets call mode a moment after capture starts
            h.postDelayed(new Runnable() {
                @Override
                public void run() {
                    try {
                        am.stopBluetoothSco();
                        am.setBluetoothScoOn(false);
                        am.setMode(AudioManager.MODE_NORMAL);
                    } catch (Exception ignored) { }
                }
            }, delay);
        }
    }

    private class Bridge {
        @JavascriptInterface
        public void micStarted() { runOnUiThread(new Runnable() { @Override public void run() { keepMusicMode(); } }); }
    }

    @Override
    protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request != REQ_FILES || fileCallback == null) return;
        Uri[] picked = null;
        if (result == RESULT_OK && data != null) {
            if (data.getClipData() != null) {
                int n = data.getClipData().getItemCount();
                picked = new Uri[n];
                for (int i = 0; i < n; i++) picked[i] = data.getClipData().getItemAt(i).getUri();
            } else if (data.getData() != null) {
                picked = new Uri[]{data.getData()};
            }
        }
        fileCallback.onReceiveValue(picked);
        fileCallback = null;
    }

    @Override
    public void onRequestPermissionsResult(int request, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(request, permissions, results);
        if (request != REQ_MIC || pendingMic == null) return;
        if (results.length > 0 && results[0] == PackageManager.PERMISSION_GRANTED) {
            pendingMic.grant(new String[]{PermissionRequest.RESOURCE_AUDIO_CAPTURE});
        } else {
            pendingMic.deny();
        }
        pendingMic = null;
    }

    @Override
    protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out);
        web.saveState(out);
    }

    @Override
    protected void onPause() {
        super.onPause();
        web.onPause();      // stops playback when the app goes to the background
    }

    @Override
    protected void onResume() {
        super.onResume();
        web.onResume();
    }
}
