package com.hojung1231.hwaeumwang;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.media.AudioDeviceInfo;
import android.media.AudioFormat;
import android.media.AudioManager;
import android.media.AudioRecord;
import android.media.MediaRecorder;
import android.net.Uri;
import android.os.Bundle;
import android.util.Base64;
import android.view.WindowManager;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import androidx.core.content.FileProvider;
import androidx.webkit.WebViewAssetLoader;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

/**
 * The whole interface is the bundled web page.  This activity gives it a secure origin and a file
 * picker, listens to the microphone on its behalf, and keeps the app up to date.
 */
public class MainActivity extends Activity {
    private static final String START = "https://appassets.androidplatform.net/assets/www/index.html";
    private static final String RELEASE = "https://github.com/hojung1231/qwer/releases/download/hwaeumwang-preview/";
    private static final int REQ_FILES = 1, REQ_MIC = 2;
    private static final int MIC_RATE = 44100, MIC_CHUNK = 2048;

    private WebView web;
    private ValueCallback<Uri[]> fileCallback;
    private volatile boolean micOn;
    private Thread micThread;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);   // practising takes minutes without touching the screen
        setVolumeControlStream(AudioManager.STREAM_MUSIC);
        web = new WebView(this);
        web.setBackgroundColor(0xFF0C0C10);
        setContentView(web);

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);                       // localStorage and IndexedDB keep the library on the device
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(true);

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

        web.addJavascriptInterface(new Bridge(), "Android");
        if (state == null) web.loadUrl(START); else web.restoreState(state);
        checkForUpdate();
    }

    // ------------------------------------------------------------------ microphone
    // The page does not open the microphone itself.  A web page that captures audio is treated by
    // Android as a phone call: playback drops to call volume and a Bluetooth headset switches to
    // its call link and its own microphone.  Recording here, as plain audio from the phone's
    // built-in microphone, leaves the music alone, and the samples are handed to the page.
    private class Bridge {
        @JavascriptInterface
        public void micStart() {
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) startMic();
                    else requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, REQ_MIC);
                }
            });
        }

        @JavascriptInterface
        public void micStop() { stopMic(); }

        @JavascriptInterface
        public String version() { return BuildConfig.VERSION_NAME; }

        /** How Android is routing sound right now, for the status line at the bottom of the page. */
        @JavascriptInterface
        public String audioInfo() {
            try {
                AudioManager am = (AudioManager) getSystemService(Context.AUDIO_SERVICE);
                int mode = am.getMode();
                String m = mode == AudioManager.MODE_NORMAL ? "일반" : mode == AudioManager.MODE_IN_COMMUNICATION ? "통화" : mode == AudioManager.MODE_IN_CALL ? "전화" : String.valueOf(mode);
                String out = "";
                for (AudioDeviceInfo d : am.getDevices(AudioManager.GET_DEVICES_OUTPUTS)) {
                    int t = d.getType();
                    if (t == AudioDeviceInfo.TYPE_BLUETOOTH_A2DP) out += " 블루투스(음악)";
                    else if (t == AudioDeviceInfo.TYPE_BLUETOOTH_SCO) out += " 블루투스(통화)";
                    else if (t == AudioDeviceInfo.TYPE_BLE_HEADSET || t == AudioDeviceInfo.TYPE_BLE_SPEAKER) out += " 블루투스(LE)";
                    else if (t == AudioDeviceInfo.TYPE_WIRED_HEADSET || t == AudioDeviceInfo.TYPE_WIRED_HEADPHONES || t == AudioDeviceInfo.TYPE_USB_HEADSET) out += " 유선";
                }
                return "모드 " + m + " · 통화연결 " + (am.isBluetoothScoOn() ? "켜짐" : "꺼짐") + " · 미디어음량 "
                        + am.getStreamVolume(AudioManager.STREAM_MUSIC) + "/" + am.getStreamMaxVolume(AudioManager.STREAM_MUSIC)
                        + " · 연결:" + (out.isEmpty() ? " 없음" : out);
            } catch (Exception e) {
                return "";
            }
        }
    }

    private void tellPage(final String js) {
        web.post(new Runnable() { @Override public void run() { web.evaluateJavascript(js, null); } });
    }

    private void startMic() {
        if (micOn) { tellPage("window.__micState&&__micState('on'," + MIC_RATE + ")"); return; }
        micOn = true;
        micThread = new Thread(new Runnable() {
            @Override
            public void run() {
                AudioRecord rec = null;
                try {
                    int min = AudioRecord.getMinBufferSize(MIC_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT);
                    AudioManager am = (AudioManager) getSystemService(Context.AUDIO_SERVICE);
                    // Not VOICE_RECOGNITION or VOICE_COMMUNICATION: with a Bluetooth headset connected those
                    // make Android open the headset's call link, and playback then drops to call quality
                    // and call volume.  UNPROCESSED (or plain MIC) records from the phone and leaves the
                    // headset playing music.
                    boolean raw = "true".equals(am.getProperty(AudioManager.PROPERTY_SUPPORT_AUDIO_SOURCE_UNPROCESSED));
                    rec = new AudioRecord(raw ? MediaRecorder.AudioSource.UNPROCESSED : MediaRecorder.AudioSource.MIC, MIC_RATE,
                            AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, Math.max(min, MIC_CHUNK * 4));
                    try { am.stopBluetoothSco(); am.setBluetoothScoOn(false); am.setMode(AudioManager.MODE_NORMAL); } catch (Exception ignored) { }
                    for (AudioDeviceInfo d : am.getDevices(AudioManager.GET_DEVICES_INPUTS)) {
                        if (d.getType() == AudioDeviceInfo.TYPE_BUILTIN_MIC) { rec.setPreferredDevice(d); break; }   // not the headset's
                    }
                    if (rec.getState() != AudioRecord.STATE_INITIALIZED) throw new IllegalStateException("init");
                    rec.startRecording();
                    tellPage("window.__micState&&__micState('on'," + MIC_RATE + ")");
                    short[] buf = new short[MIC_CHUNK];
                    ByteBuffer bytes = ByteBuffer.allocate(MIC_CHUNK * 2).order(ByteOrder.LITTLE_ENDIAN);
                    while (micOn) {
                        int n = 0;
                        while (n < MIC_CHUNK && micOn) {
                            int r = rec.read(buf, n, MIC_CHUNK - n);
                            if (r <= 0) break;
                            n += r;
                        }
                        if (n < MIC_CHUNK) continue;
                        bytes.clear();
                        bytes.asShortBuffer().put(buf);
                        tellPage("window.__mic&&__mic('" + Base64.encodeToString(bytes.array(), Base64.NO_WRAP) + "')");
                    }
                } catch (Exception e) {
                    tellPage("window.__micState&&__micState('error',0)");
                } finally {
                    micOn = false;
                    if (rec != null) { try { rec.stop(); } catch (Exception ignored) { } rec.release(); }
                }
            }
        }, "mic");
        micThread.start();
    }

    private void stopMic() { micOn = false; }

    @Override
    public void onRequestPermissionsResult(int request, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(request, permissions, results);
        if (request != REQ_MIC) return;
        if (results.length > 0 && results[0] == PackageManager.PERMISSION_GRANTED) startMic();
        else tellPage("window.__micState&&__micState('denied',0)");
    }

    // ------------------------------------------------------------------ files
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

    // ------------------------------------------------------------------ updates
    // Each build publishes version.json next to the APK.  On launch the app compares it with its
    // own build number and offers the newer APK; Android itself then asks to confirm the install.
    private void checkForUpdate() {
        new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    JSONObject v = new JSONObject(new String(fetch(RELEASE + "version.json", null), "UTF-8"));
                    final int code = v.getInt("versionCode");
                    final String name = v.optString("versionName", "");
                    if (code <= BuildConfig.VERSION_CODE) return;
                    runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            if (isFinishing()) return;
                            new AlertDialog.Builder(MainActivity.this)
                                    .setTitle("새 버전이 있습니다")
                                    .setMessage("화음왕 " + name + " 버전이 나왔습니다. 지금 업데이트할까요?\n(현재 " + BuildConfig.VERSION_NAME + ")")
                                    .setNegativeButton("나중에", null)
                                    .setPositiveButton("업데이트", (d, w) -> downloadUpdate())
                                    .show();
                        }
                    });
                } catch (Exception ignored) { }      // offline, or nothing published: start as usual
            }
        }, "update-check").start();
    }

    private void downloadUpdate() {
        final AlertDialog progress = new AlertDialog.Builder(this).setTitle("업데이트 받는 중").setMessage("0%").setCancelable(false).show();
        new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    File dir = new File(getCacheDir(), "updates");
                    dir.mkdirs();
                    final File apk = new File(dir, "hwaeumwang.apk");
                    OutputStream out = new FileOutputStream(apk);
                    fetch(RELEASE + "hwaeumwang.apk", new Sink(out, progress));
                    out.close();
                    runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            progress.dismiss();
                            Uri uri = FileProvider.getUriForFile(MainActivity.this, "com.hojung1231.hwaeumwang.files", apk);
                            Intent install = new Intent(Intent.ACTION_VIEW);
                            install.setDataAndType(uri, "application/vnd.android.package-archive");
                            install.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
                            startActivity(install);
                        }
                    });
                } catch (Exception e) {
                    runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            progress.dismiss();
                            new AlertDialog.Builder(MainActivity.this).setTitle("업데이트를 받지 못했습니다")
                                    .setMessage("인터넷 연결을 확인한 뒤 앱을 다시 열어 주세요.").setPositiveButton("확인", null).show();
                        }
                    });
                }
            }
        }, "update-download").start();
    }

    /** Receives a download and shows how far along it is. */
    private class Sink {
        final OutputStream out; final AlertDialog dialog; long done; int shown = -1;
        Sink(OutputStream out, AlertDialog dialog) { this.out = out; this.dialog = dialog; }
        void write(byte[] b, int n, long total) throws Exception {
            out.write(b, 0, n);
            done += n;
            final int pct = total > 0 ? (int) (done * 100 / total) : -1;
            if (pct != shown) {
                shown = pct;
                runOnUiThread(new Runnable() { @Override public void run() { dialog.setMessage(pct >= 0 ? pct + "%" : (done / 1024) + " KB"); } });
            }
        }
    }

    /** GET a URL, following redirects.  With a sink the body is streamed to it; without, it is returned. */
    private byte[] fetch(String address, Sink sink) throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL(address).openConnection();
        c.setConnectTimeout(8000);
        c.setReadTimeout(20000);
        c.setInstanceFollowRedirects(true);
        c.setRequestProperty("Cache-Control", "no-cache");
        try {
            if (c.getResponseCode() != 200) throw new IllegalStateException("HTTP " + c.getResponseCode());
            long total = c.getContentLengthLong();
            InputStream in = c.getInputStream();
            ByteArrayOutputStream mem = sink == null ? new ByteArrayOutputStream() : null;
            byte[] b = new byte[16384];
            int n;
            while ((n = in.read(b)) > 0) {
                if (sink != null) sink.write(b, n, total); else mem.write(b, 0, n);
            }
            in.close();
            return mem == null ? null : mem.toByteArray();
        } finally {
            c.disconnect();
        }
    }

    // ------------------------------------------------------------------ lifecycle
    @Override
    protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out);
        web.saveState(out);
    }

    @Override
    protected void onPause() {
        super.onPause();
        stopMic();
        web.onPause();      // stops playback when the app goes to the background
    }

    @Override
    protected void onResume() {
        super.onResume();
        web.onResume();
    }
}
