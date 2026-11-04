const fs=require('node:fs');
const path=require('node:path');
const {withDangerousMod}=require('expo/config-plugins');
const marker='// BOGO_ANDROID_TAP_FOCUS';
const addition=`
  ${marker}
  override fun dispatchTouchEvent(event: android.view.MotionEvent): Boolean {
    if (event.action == android.view.MotionEvent.ACTION_UP) {
      camera?.let { activeCamera ->
        runCatching {
          val point = previewView.meteringPointFactory.createPoint(event.x, event.y)
          val action = FocusMeteringAction.Builder(
            point,
            FocusMeteringAction.FLAG_AF or FocusMeteringAction.FLAG_AE
          ).setAutoCancelDuration(3, java.util.concurrent.TimeUnit.SECONDS).build()
          if (activeCamera.cameraInfo.isFocusMeteringSupported(action)) {
            activeCamera.cameraControl.startFocusAndMetering(action)
          }
        }
      }
    }
    return super.dispatchTouchEvent(event)
  }

`;
function patchCameraSource(source){if(source.includes(marker))return source;const anchor='  private fun startFocusMetering() {';if(!source.includes(anchor))throw Error('expo-camera source changed: review tap-focus integration before building.');return source.replace(anchor,addition+anchor);}
module.exports=config=>withDangerousMod(config,['android',async config=>{const moduleFile=require.resolve('expo-camera/package.json',{paths:[config.modRequest.projectRoot]});const file=path.join(path.dirname(moduleFile),'android/src/main/java/expo/modules/camera/ExpoCameraView.kt');fs.writeFileSync(file,patchCameraSource(fs.readFileSync(file,'utf8')));return config;}]);
module.exports.patchCameraSource=patchCameraSource;
