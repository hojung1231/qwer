const fs=require('node:fs');
const crypto=require('node:crypto');
const [apkPath,configPath,outPath]=process.argv.slice(2);
const config=JSON.parse(fs.readFileSync(configPath,'utf8'));
const app=config.expo||config;
const bytes=fs.readFileSync(apkPath);
if(!Number.isInteger(app.android.versionCode)||app.android.package!=='com.hojung1231.bogoagain')throw Error('Invalid Android build identity');
fs.writeFileSync(outPath,JSON.stringify({version:app.version,versionCode:app.android.versionCode,package:app.android.package,downloadUrl:'https://github.com/hojung1231/qwer/releases/download/android-preview/bogo-again-android.apk',size:bytes.length,sha256:crypto.createHash('sha256').update(bytes).digest('hex')},null,2));
