#!/usr/bin/env bash
set -euo pipefail
mkdir -p touch-test/classes touch-test/dex
ANDROID_JAR="$ANDROID_HOME/platforms/android-35/android.jar"
TOOLS="$(find "$ANDROID_HOME/build-tools" -name aapt2 | sort -V | tail -n 1)"
TOOLS="${TOOLS%/aapt2}"
cat > touch-test/AndroidManifest.xml <<'XML'
<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="com.bogo.touch">
  <uses-sdk android:minSdkVersion="26" android:targetSdkVersion="35"/>
  <application android:debuggable="true" android:label="Bogo gesture test">
    <activity android:name="com.bogo.touch.ShareReceiver" android:exported="true" android:label="Bogo share verifier">
      <intent-filter>
        <action android:name="android.intent.action.SEND"/>
        <category android:name="android.intent.category.DEFAULT"/>
        <data android:mimeType="image/jpeg"/>
        <data android:mimeType="text/plain"/>
      </intent-filter>
    </activity>
  </application>
  <instrumentation android:name="com.bogo.touch.Touch" android:targetPackage="com.bogo.touch"/>
</manifest>
XML
javac -source 8 -target 8 -cp "$ANDROID_JAR" -d touch-test/classes scripts/Touch.java scripts/ShareReceiver.java
"$TOOLS/d8" --lib "$ANDROID_JAR" --output touch-test/dex touch-test/classes/com/bogo/touch/*.class
"$TOOLS/aapt2" link --manifest touch-test/AndroidManifest.xml -I "$ANDROID_JAR" -o touch-test/test.apk
(cd touch-test/dex && zip -q ../test.apk classes.dex)
keytool -genkeypair -keystore touch-test/key.jks -storepass android -keypass android -alias test -keyalg RSA -dname CN=Test -validity 3 -noprompt
"$TOOLS/apksigner" sign --ks touch-test/key.jks --ks-pass pass:android touch-test/test.apk
adb install -t touch-test/test.apk
