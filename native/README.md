# 보고또보고 Android 앱

React Native 0.88 / Expo SDK 58 / TypeScript로 작성한 설치형 앱입니다. WebView를 사용하지 않습니다. JavaScript 실행 코드를 APK에 포함하므로 Expo Go와 개발 PC가 필요하지 않습니다.

카메라와 영상은 expo-camera, 녹음은 expo-audio, 기기 보관은 SQLite와 앱 전용 파일 공간, API 키는 SecureStore, PDF 공유는 expo-print와 Android 공유창을 사용합니다. 음성 텍스트 입력은 갤럭시 키보드의 마이크를 사용합니다.

## 설치

GitHub 저장소 Releases의 `android-preview`에서 `보고또보고-Android.apk`를 휴대폰으로 내려받아 설치합니다. 앱은 출시 전 미리보기 서명으로 빌드합니다. Play 스토어 배포용 서명은 별도 준비해야 합니다. 최초 설치 시 Android가 다운로드 출처의 앱 설치 허용을 요청할 수 있습니다. 카메라·마이크 권한은 사용 시 요청합니다.

## 개발 / 빌드

`npm ci`, `npx tsc --noEmit`, `npx expo prebuild --platform android --no-install` 순으로 실행합니다. Android SDK와 JDK 17이 필요합니다. `android` 폴더에서 `./gradlew :app:assembleRelease -PreactNativeArchitectures=arm64-v8a,x86_64`로 독립 실행 APK를 만듭니다. GitHub Actions가 같은 절차로 빌드해 릴리스에 APK를 첨부합니다.

## 사내 Qwen

설정에서 ‘사내 Qwen’을 선택하고 사용자가 제공한 서버 기본 주소를 입력한 뒤 ‘연결 확인 · 모델 불러오기’를 누릅니다. `/api/models`에서 Qwen 모델을 선택하고 저장하세요. 앱이 `/api/chat` SSE를 직접 처리합니다. 사내망 또는 VPN 접근이 필요합니다. 서버 주소는 공개 소스에 포함하지 않습니다.

사내 HTTP 서버 호환을 위해 Android 앱은 cleartext 연결을 허용하되, 앱 코드에서는 사설 IPv4 주소에만 HTTP를 허용합니다. API 키가 있는 서버는 HTTPS를 요구합니다. HTTP는 암호화되지 않으므로 사내 정책에 맞춰 사용하세요. 앱은 외부 Claude 모델을 선택하지 않으며 GPT로 자동 대체하지 않습니다.

## 기록 보관

기록과 설정은 기기에 보관합니다. 앱 삭제 시 지워질 수 있으므로 프로젝트 백업을 공유해 파일로 보관하세요. 네이티브 백업은 웹앱 백업과 별도 형식입니다. 되돌리기는 현재 작업에서 최근 20회 변경을 보관합니다. 영상과 음성 녹음은 3분으로 제한합니다. 촬영창을 터치하면 CameraX의 해당 위치에 초점 및 노출 측정을 요청합니다. 하드웨어가 지원하는 경우에 적용됩니다. Expo config plugin으로 Android 촬영 뷰를 확장했습니다.

PDF 공유에서 설치된 카카오톡을 선택할 수 있습니다. 영상과 음성 원본을 AI에 보내지 않으며 메모와 선택한 사진을 사용합니다. 실제 기기 카메라·마이크 및 모델의 사진 정확도는 설치 후 확인해야 합니다.
