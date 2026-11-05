"""Android emulator UI verification against the freshly built APK."""
import base64,io,json,pathlib,re,struct,subprocess,time,wave,zlib,xml.etree.ElementTree as ET

def adb(*args):
    return subprocess.check_output(['adb', *map(str,args)]).decode('utf-8', errors='replace')

def tree():
    adb('shell','uiautomator','dump','/sdcard/window.xml')
    return ET.fromstring(adb('shell','cat','/sdcard/window.xml'))

def bounds(node):
    return tuple(map(int,re.findall(r'\d+',node.attrib['bounds'])))

def find(label):
    root=tree()
    for attribute in ('content-desc','text'):
        for node in root.iter('node'):
            if node.attrib.get(attribute)==label:
                x1,y1,x2,y2=bounds(node)
                if x2>x1 and y2>y1:return node
    return None

def tap(label):
    for attempt in range(8):
        node=find(label)
        if node is not None:
            x1,y1,x2,y2=bounds(node);adb('shell','input','tap',(x1+x2)//2,(y1+y2)//2);time.sleep(1);return
        if attempt==0:top()
        else:adb('shell','input','swipe',540,1850,540,850,450)
        time.sleep(.5)
    raise AssertionError('Missing UI: '+label)

def screenshot(name):
    pathlib.Path(name).write_bytes(subprocess.check_output(['adb','exec-out','screencap','-p']))

def contains(text):
    return any(text in (n.attrib.get('text','')+' '+n.attrib.get('content-desc','')) for n in tree().iter('node'))

def top():
    for _ in range(2):adb('shell','input','swipe',540,650,540,1950,350)
    time.sleep(.5)

def tap_node(node):
    x1,y1,x2,y2=bounds(node);adb('shell','input','tap',(x1+x2)//2,(y1+y2)//2);time.sleep(1)

def make_fixture():
    def chunk(kind,body):return struct.pack('>I',len(body))+kind+body+struct.pack('>I',zlib.crc32(kind+body)&0xffffffff)
    width,height=3200,2400
    row=b'\0'+bytes([210,220,200])*width
    png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(row*height))+chunk(b'IEND',b'')
    audio=io.BytesIO()
    with wave.open(audio,'wb') as wav:wav.setparams((1,2,16000,0,'NONE','NONE'));wav.writeframes(b'\0'*32000)
    fixture={'format':'bogo-native-v1','project':{'title':'HighRes Fixture','items':[{'type':'image','memo':'Original 3200x2400 photo with audio','mediaBase64':base64.b64encode(png).decode(),'audioBase64':base64.b64encode(audio.getvalue()).decode(),'audioExtension':'wav'}]}}
    pathlib.Path('bogo-highres.bogo.json').write_text(json.dumps(fixture))
    adb('push','bogo-highres.bogo.json','/sdcard/Download/bogo-highres.bogo.json')
    adb('shell','mkdir','-p','/sdcard/Documents/BogoTest')

def jpeg_size(path):
    data=pathlib.Path(path).read_bytes();pos=2
    while pos<len(data):
        if data[pos]!=255:pos+=1;continue
        marker=data[pos+1];pos+=2
        if marker in (0xd8,0xd9):continue
        size=int.from_bytes(data[pos:pos+2],'big')
        if marker in (0xc0,0xc1,0xc2):return (int.from_bytes(data[pos+5:pos+7],'big'),int.from_bytes(data[pos+3:pos+5],'big'))
        pos+=size
    raise AssertionError('JPEG dimensions not found')

def gesture(mode,box,start,end):
    x1,y1,x2,y2=box
    arguments={'mode':mode,'x1':start[0],'y1':start[1],'x2':end[0],'y2':end[1],'left':x1,'top':y1,'width':x2-x1,'height':y2-y1}
    command=['shell','am','instrument','-w']
    for key,value in arguments.items():command+=['-e',key,str(value)]
    output=adb(*command,'com.bogo.touch/com.bogo.touch.Touch')
    assert ('stable=true' if mode=='resize' else 'deleted=true') in output,output
    time.sleep(1)

verified=[]
try:
    assert contains('새 작업 시작')
    assert contains('앱 업데이트')
    screenshot('android-home.png');verified.append('home-and-update-button')
    tap('새 작업 시작')
    assert contains('4:3')
    tap('촬영 비율 회전');top();assert contains('3:4')
    tap('촬영 비율 회전');top();assert contains('4:3')
    assert not contains('이어서 촬영')
    top();screenshot('android-capture.png');verified.append('capture-4x3-rotation')
    tap('사진 촬영');time.sleep(4);top()
    assert contains('현장 기록 1 선택')
    tap('사진 촬영');time.sleep(3);top()
    assert contains('현장 기록 2 선택')
    first,second=bounds(find('현장 기록 1 선택')),bounds(find('현장 기록 2 선택'))
    overlap=(first[2]-second[0])/(first[2]-first[0])
    assert .25<overlap<.35,overlap
    verified.append('repeat-shutter-and-thumbnail-overlap')
    tap('현장 기록 1 선택');tap('사진 편집 열기');time.sleep(3)
    tap('원 개체 선택')
    x1,y1,x2,y2=bounds(find('사진 편집 캔버스'))
    adb('shell','input','swipe',int(x1+(x2-x1)*.25),int(y1+(y2-y1)*.3),int(x1+(x2-x1)*.6),int(y1+(y2-y1)*.7),400)
    time.sleep(1);assert contains('개체 1')
    tap('노란색 윤곽선');screenshot('android-editor.png')
    tap('편집 사진 저장');time.sleep(4)
    tap('사진 편집 열기');time.sleep(3)
    assert contains('개체 1')
    tap('사진 편집 닫기');time.sleep(3)
    verified.append('landscape-annotation-save-and-reopen')
    # A text-only field record verifies native navigation and persistent report generation.
    node=find('현장 메모')
    if node is None:
        adb('shell','input','swipe',540,1800,540,900,450);time.sleep(1)
    tap('현장 메모')
    adb('shell','input','text','Inspection%ssample%stwo%sscratches')
    adb('shell','input','keyevent','4');time.sleep(1)
    adb('shell','input','swipe',540,650,540,1800,450);time.sleep(1)
    tap('보고서 모드');tap('보고서 작성')
    assert contains('Inspection sample two scratches')
    assert contains('현장 확인 내용')
    screenshot('android-report.png');verified.append('native-report-generation')
    tap('홈')
    assert contains('내 라이브러리 1')
    verified.append('saved-project-library')
    make_fixture();tap('복원');time.sleep(2)
    if find('bogo-highres.bogo.json') is None:
        tap('Show roots');tap('Downloads')
    tap('bogo-highres.bogo.json');time.sleep(2);tap('확인')
    tap('HighRes Fixture');tap('현장 기록 1 선택');tap('사진 편집 열기');time.sleep(3)
    tap('원 개체 선택');box=bounds(find('사진 편집 캔버스'));x1,y1,x2,y2=box
    def point(x,y):return (int(x1+(x2-x1)*x),int(y1+(y2-y1)*y))
    gesture('resize',box,point(.1,.1),point(.4,.4));assert contains('개체 1')
    tap('사각형 개체 선택');gesture('resize',box,point(.58,.52),point(.9,.85));assert contains('개체 2')
    gesture('delete',box,point(.25,.25),point(.25,.25));assert contains('개체 1')
    verified.append('real-two-finger-release-stability-circle-and-rectangle')
    screenshot('android-editor.png');tap('편집 사진 저장');time.sleep(3)
    tap('폴더 저장');time.sleep(2)
    if find('Documents') is None:
        tap('Show roots')
        root=tree()
        internal=next((n for n in root.iter('node') if any(v in n.attrib.get('text','') for v in ['sdk_gphone','Internal storage','Pixel 6'])),None)
        assert internal is not None,ET.tostring(root,encoding='unicode')
        tap_node(internal)
    tap('Documents');tap('BogoTest');tap('Use this folder');tap('Allow');time.sleep(4)
    assert contains('폴더 저장 완료');screenshot('android-folder.png');tap('확인')
    adb('pull','/sdcard/Documents/BogoTest','folder-output')
    manifests=list(pathlib.Path('folder-output').rglob('프로젝트.json'));assert len(manifests)==1
    manifest=json.loads(manifests[0].read_text());record=manifest['project']['items'][0];folder=manifests[0].parent
    assert jpeg_size(folder/record['uri'])==(3200,2400)
    assert (folder/record['audioUri']).stat().st_size>32000
    assert (folder/record['originalUri']).stat().st_size>0
    assert record['annotations'][0]['number']==1
    assert record['annotations'][0]['kind']=='rectangle'
    verified.append('full-resolution-3200x2400-with-original-audio-folder-export')
finally:
    pathlib.Path('android-ui-verification.json').write_text(json.dumps({'verified':verified},ensure_ascii=False,indent=2),encoding='utf-8')
    pathlib.Path('window.xml').write_text(ET.tostring(tree(),encoding='unicode'),encoding='utf-8')
    screenshot('android-final.png')
