"""Android emulator UI verification against the freshly built APK."""
import base64,hashlib,io,json,pathlib,re,struct,subprocess,time,wave,queue,threading,zlib,xml.etree.ElementTree as ET

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
            value=node.attrib.get(attribute,'').casefold()
            if value==label.casefold() or label.startswith('프로젝트 선택, ') and value.startswith(label.casefold()+',') or label=='수신 모드' and value.startswith('수신 모드'):
                x1,y1,x2,y2=bounds(node)
                if x2>x1 and y2>y1:return node
    return None

def tap(label):
    for attempt in range(8):
        node=find(label)
        if node is not None:
            x1,y1,x2,y2=bounds(node);adb('shell','input','tap',(x1+x2)//2,(y1+y2)//2);time.sleep(1);return
        if label.endswith('개체 선택'):
            adb('shell','input','swipe',180,750,180,330,400)
        elif attempt==0:top()
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
    expected='axisStable=true' if mode.startswith('axis-') else 'pinchStable=true' if mode.startswith('pinch') else 'movedWithoutTrash=true' if mode=='move-no-trash' else 'projectStable=true' if mode.startswith('project') else 'stripStable=true' if mode.startswith('strip') else 'stable=true' if mode.startswith('resize') else 'deleted=true'
    assert expected in output,output
    time.sleep(1)

def create_project(name,first=False):
    top();tap('새 프로젝트 폴더');tap('프로젝트 폴더 이름')
    adb('shell','input','text',name);tap('프로젝트 만들기');time.sleep(2)
    if first:
        if find('BogoTest') is None:
            if find('Documents') is None:
                tap('Show roots')
                root=tree()
                internal=next((n for n in root.iter('node') if any(v in n.attrib.get('text','') for v in ['sdk_gphone','Internal storage','Pixel 6'])),None)
                assert internal is not None,ET.tostring(root,encoding='unicode')
                tap_node(internal)
            tap('Documents')
        tap('BogoTest');tap('Use this folder');tap('Allow');time.sleep(2)
    assert find('프로젝트 선택, '+name) is not None

def swipe_project(current,target,direction):
    box=bounds(find('프로젝트 선택, '+current));x=(box[0]+box[2])//2;y=(box[1]+box[3])//2
    gesture('project',box,(x,y),(x,y+direction*120))
    assert find('프로젝트 선택, '+target) is not None,(current,target)

verified=[]
build_code=int(re.search(r'versionCode=(\d+)',adb('shell','dumpsys','package','com.hojung1231.bogoagain')).group(1))
diagnostic_old_build=build_code==9
try:
    # Cold-booted CI emulators occasionally show the launcher's own ANR dialog.
    # Dismiss only that system dialog; app ANRs must still fail verification.
    if contains("Pixel Launcher isn't responding"):
        tap('Close app')
        adb('shell','am','start','-W','-n','com.hojung1231.bogoagain/.MainActivity')
        time.sleep(3)
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
    tap('촬영 비율 회전');top()
    adb('shell','input','swipe',800,1850,800,1250,400);time.sleep(1)
    frame=bounds(find('촬영 프레임'));rotate=bounds(find('촬영 비율 회전'))
    assert abs((frame[2]-frame[0])/(frame[3]-frame[1])-.75)<.02,frame
    assert not any(n.attrib.get('text') in ('세로','가로') for n in tree().iter('node')),'Rotation button still has visible text'
    assert rotate[0]>frame[0]+(frame[2]-frame[0])*.7 and rotate[1]>frame[1]+(frame[3]-frame[1])*.8
    screenshot('android-portrait.png')
    tap('사진 촬영');time.sleep(3);top();assert contains('현장 기록 3 선택')
    tap('촬영 비율 회전');top()
    verified.append('real-3x4-portrait-capture-frame-and-bottom-right-rotation')
    first,second=bounds(find('현장 기록 1 선택')),bounds(find('현장 기록 2 선택'))
    overlap=(first[2]-second[0])/(first[2]-first[0])
    assert .25<overlap<.35,overlap
    verified.append('repeat-shutter-and-thumbnail-overlap')
    # Build 9's known cancel-recovery failure is diagnosed separately; continue exercising other new features.
    for mode in (('strip',) if diagnostic_old_build else ('strip','strip-cancel')):
        first,second=bounds(find('현장 기록 1 선택')),bounds(find('현장 기록 2 선택'))
        # Diagonal wobble exceeds Android's native scroll touch slop while selecting left/right.
        start=((first[0]+first[2])//2,(first[1]+first[3])//2)
        end=((second[0]+second[2])//2,start[1])
        gesture(mode,first,start,end)
        assert find('현장 기록 2 선택').attrib.get('selected')=='true'
        old=bounds(find('작업 제목'))
        adb('shell','input','swipe',750,1850,750,1250,400);time.sleep(1)
        title=find('작업 제목')
        assert title is None or bounds(title)[1]<old[1]-20,'Vertical scrolling stayed locked after '+mode
        top()
    screenshot('android-strip-drag.png')
    verified.append('thumbnail-drag-with-vertical-wobble-and-scroll-unlock-after-up'+('' if diagnostic_old_build else '-and-cancel'))
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
    # The only memo input now lives directly below the photo preview.
    top();tap('사진 메모 텍스트')
    adb('shell','input','text','Inspection%ssample%stwo%sscratches')
    adb('shell','input','keyevent','4');time.sleep(1)
    assert contains('Inspection sample two scratches')
    assert find('현장 메모') is None and not contains('보고서 모드')
    tap('메모 텍스트 초기화');assert find('사진 메모 텍스트').attrib.get('text','')==''
    tap('되돌리기');assert contains('Inspection sample two scratches')
    tap('AI');tap('취소');assert contains('Inspection sample two scratches')
    tap('AI');tap('정리');assert contains('개인 OpenAI API 키');tap('OK')
    assert contains('Inspection sample two scratches')
    verified.append('inline-editable-transcript-clear-undo-and-opt-in-AI-keeps-original-without-key')
    tap('홈')
    assert contains('내 라이브러리 1')
    verified.append('saved-project-library')
    make_fixture();tap('복원');time.sleep(2)
    if find('bogo-highres.bogo.json') is None:
        tap('Show roots');tap('Downloads')
    tap('bogo-highres.bogo.json');time.sleep(2);tap('OK')
    tap('HighRes Fixture');tap('현장 기록 1 선택');tap('사진 편집 열기');time.sleep(3)
    tap('원 개체 선택');box=bounds(find('사진 편집 캔버스'));x1,y1,x2,y2=box
    def point(x,y):return (int(x1+(x2-x1)*x),int(y1+(y2-y1)*y))
    gesture('resize',box,point(.1,.1),point(.4,.4));assert contains('개체 1')
    assert find('선택 개체 선택').attrib.get('selected')=='true'
    mic=bounds(find('편집 중 음성 메모'))
    assert mic[0]>x2 and mic[1]>=y2,'Voice memo is not at the bottom right'
    gesture('axis-vertical',box,point(.25,.04),point(.25,.48));assert contains('개체 1')
    gesture('axis-horizontal',box,point(.04,.25),point(.48,.25));assert contains('개체 1')
    verified.append('region-based-independent-width-and-height-resize-with-two-finger-pan-and-stable-release')
    gesture('pinch-wide',box,point(.04,.04),point(.48,.48));assert contains('개체 1')
    gesture('pinch-narrow',box,point(.2,.2),point(.34,.34));assert contains('개체 1')
    verified.append('relative-pinch-scale-with-wide-and-narrow-grips-no-initial-jump-and-stable-release')
    gesture('move-no-trash',box,point(.25,.25),point(.25,.25));assert contains('개체 1')
    verified.append('one-finger-object-movement-does-not-open-trash')
    tap('사각형 개체 선택');gesture('resize',box,point(.7,.62),point(.94,.9));assert contains('개체 2')
    assert find('선택 개체 선택').attrib.get('selected')=='true'
    gesture('delete',box,point(.25,.25),point(.25,.25));assert contains('개체 1')
    verified.append('real-two-finger-release-stability-circle-and-rectangle')
    verified.append('stationary-hold-reveals-trash-at-bottom-right-and-drag-deletes')
    tap('화살표 개체 선택');gesture('resize',box,point(.92,.25),point(.58,.08));assert contains('개체 2')
    assert find('선택 개체 선택').attrib.get('selected')=='true'
    verified.append('tool-rail-returns-to-select-and-voice-memo-is-bottom-right')
    screenshot('android-editor.png');tap('편집 사진 저장');time.sleep(3)
    create_project('Project1',True);create_project('Project2');create_project('Project3')
    swipe_project('Project3','Project2',1);swipe_project('Project2','Project1',1)
    swipe_project('Project1','Project2',-1);swipe_project('Project2','Project3',-1)
    swipe_project('Project3','Project2',1)
    screenshot('android-project-wheel.png');verified.append('project-wheel-down-selects-previous-up-selects-next')
    tap('저장');time.sleep(4)
    assert contains('프로젝트 저장 완료');screenshot('android-folder.png');tap('OK')
    adb('pull','/sdcard/Documents/BogoTest','folder-output')
    manifests=list(pathlib.Path('folder-output').rglob('프로젝트.json'));assert len(manifests)==1
    manifest=json.loads(manifests[0].read_text());record=manifest['project']['items'][0];folder=manifests[0].parent
    assert folder.parent.name=='Project2' and folder.parent.parent.name=='보고또보고'
    assert sorted(p.name for p in folder.parent.parent.iterdir() if p.is_dir())==['Project1','Project2','Project3']
    assert not list((folder.parent.parent/'Project1').rglob('프로젝트.json'))
    assert not list((folder.parent.parent/'Project3').rglob('프로젝트.json'))
    verified.append('dedicated-app-root-project-folder-record-set-hierarchy')
    assert jpeg_size(folder/record['uri'])==(3200,2400)
    assert (folder/record['audioUri']).stat().st_size>32000
    assert (folder/record['originalUri']).stat().st_size>0
    assert record['annotations'][0]['number']==1
    assert record['annotations'][0]['kind']=='rectangle'
    arrow=record['annotations'][1];assert arrow['kind']=='arrow' and arrow['x1']>arrow['x2'] and arrow['y1']>arrow['y2']
    verified.append('first-touch-anchors-arrow-shaft')
    verified.append('full-resolution-3200x2400-with-original-audio-folder-export')
    before=(folder/record['uri']).read_bytes()
    tap('사진 편집 열기');time.sleep(3)
    box=bounds(find('사진 편집 캔버스'));x1,y1,x2,y2=box
    adb('shell','input','tap',int(x1+(x2-x1)*.74),int(y1+(y2-y1)*.68));time.sleep(1)
    tap('노란색 윤곽선');tap('편집 사진 저장');time.sleep(3)
    tap('저장');time.sleep(3);assert contains('프로젝트 저장 완료');tap('OK')
    adb('pull','/sdcard/Documents/BogoTest','folder-output-updated')
    updated=list(pathlib.Path('folder-output-updated').rglob('프로젝트.json'));assert len(updated)==1
    latest=json.loads(updated[0].read_text())['project']['items'][0]
    assert latest['annotations'][0]['color']=='#f3cd39'
    output=updated[0].parent/latest['uri'];assert jpeg_size(output)==(3200,2400)
    assert output.read_bytes()!=before
    verified.append('project-folder-updates-edited-photo-without-duplicate-activity')
    tap('선택 사진 공유');time.sleep(2);screenshot('android-share.png')
    tap('Bogo share verifier');time.sleep(2)
    shared=json.loads(adb('shell','run-as','com.bogo.touch','cat','files/share-result.json'))
    assert shared['action']=='android.intent.action.SEND' and shared['mime']=='image/jpeg' and shared['count']==1,shared
    assert not shared['hasText'] and not shared['hasMultipleStreams'],shared
    assert (shared['width'],shared['height'])==(3200,2400)
    assert shared['sha256']==hashlib.sha256(output.read_bytes()).hexdigest(),shared
    pathlib.Path('android-share-verification.json').write_text(json.dumps(shared,indent=2))
    verified.append('share-exactly-one-current-edited-photo-without-report-or-audio')
    tap('홈');tap('새 외근 기록');tap('저장');time.sleep(3);tap('OK')
    adb('pull','/sdcard/Documents/BogoTest','capture-output')
    captures=[json.loads(p.read_text()) for p in pathlib.Path('capture-output').rglob('프로젝트.json') if json.loads(p.read_text())['project']['title']=='새 외근 기록']
    assert len(captures)==1
    capture_folder=next(p.parent for p in pathlib.Path('capture-output').rglob('프로젝트.json') if json.loads(p.read_text())['project']['title']=='새 외근 기록')
    photos=captures[0]['project']['items'];w,h=jpeg_size(capture_folder/photos[2]['uri']);assert abs(w/h-.75)<.002,(w,h)
    verified.append('captured-portrait-file-has-actual-3x4-pixels')
    adb('shell','am','force-stop','com.hojung1231.bogoagain')
    adb('shell','am','start','-W','-n','com.hojung1231.bogoagain/.MainActivity');time.sleep(4)
    tap('새 외근 기록');assert find('프로젝트 선택, Project2') is not None
    verified.append('project-folder-selection-and-created-folders-persist-after-restart')
    # App link and invitations use a test-only local share receiver, never real contacts.
    tap('앱 다운로드 링크 공유');tap('Bogo share verifier')
    app_share=json.loads(adb('shell','run-as','com.bogo.touch','cat','files/share-result.json'))
    assert app_share['mime']=='text/plain' and 'releases/download/android-preview/bogo-again-android.apk' in app_share['text']
    verified.append('header-app-download-link-shares-through-Android-chooser')
    tap('팀원 등록');tap('내 이름');app_test_name='BogoAppTest-'+str(time.time_ns())[-8:];adb('shell','input','text',app_test_name);pathlib.Path('team-app-fixture.json').write_text(json.dumps({'name':app_test_name}))
    tap('내 전화번호');adb('shell','input','text','01000000001');adb('shell','input','keyevent','4')
    tap('내 정보 저장');time.sleep(3)
    tap('팀원 추가');tap('추가할 팀원 이름');adb('shell','input','text','BogoPeer')
    tap('추가할 팀원 전화번호');adb('shell','input','text','01000000002');adb('shell','input','keyevent','4')
    tap('팀원 등록 저장');assert contains('BogoPeer') and contains('01000000002')
    tap('카카오톡으로 초대');tap('Bogo share verifier')
    invite_share=json.loads(adb('shell','run-as','com.bogo.touch','cat','files/share-result.json'))
    invite=re.search(r'join\.html#([a-f0-9]{64})',invite_share['text']).group(1)
    fixture=subprocess.Popen(['node','scripts/team-ui-fixture.cjs'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1)
    responses=queue.Queue()
    def read_responses():
        for line in fixture.stdout:
            if line.startswith('RPC '):responses.put(json.loads(line[4:]))
    threading.Thread(target=read_responses,daemon=True).start()
    def rpc(action,**values):
        fixture.stdin.write(json.dumps({'action':action,**values})+'\n');fixture.stdin.flush()
        try:result=responses.get(timeout=90)
        except queue.Empty:raise AssertionError('Fake-peer RPC timed out: '+action)
        assert result['ok'],result.get('error');return result['result']
    connected=rpc('connect',token=invite)
    tap('새로고침')
    for _ in range(20):
        if contains('● 연결됨'):break
        time.sleep(1)
    assert contains('● 연결됨');tap('닫기')
    adb('shell','am','start','-W','-a','android.intent.action.VIEW','-d','bogo-again://invite?token='+connected['secondInvite'],'com.hojung1231.bogoagain');time.sleep(3)
    assert contains('받은 초대로 연결');tap('초대한 팀원과 연결');time.sleep(3);tap('OK')
    assert contains('BogoPeerTwo');screenshot('android-team.png');tap('닫기')
    verified.append('team-table-manual-name-phone-and-single-use-invitation-connect-fake-peer')
    tap('홈');tap('HighRes Fixture');tap('세트 공유');tap('수신자 BogoPeer');tap('수신자 BogoPeerTwo');tap('선택한 2명에게 보내기')
    for _ in range(30):
        if contains('세트 전송 완료'):break
        time.sleep(1)
    assert contains('세트 전송 완료');tap('OK');sent=rpc('inspect');assert sent['files']>=3
    verified.append('full-set-share-to-two-selected-team-members-includes-edited-photo-original-and-audio')
    rpc('incoming')
    for _ in range(30):
        if contains('수신 모드, 새 자료 2개'):break
        time.sleep(1)
    assert contains('수신 모드, 새 자료 2개')
    tap('수신 모드')
    newest='받은 세트 최신수신프로젝트, BogoPeer, 사진 1장, 새 자료'
    older='받은 세트 이전수신프로젝트, BogoPeer, 사진 1장, 새 자료'
    assert bounds(find(newest))[1]<bounds(find(older))[1]
    assert contains('최신수신프로젝트');screenshot('android-inbox.png')
    verified.append('incoming-badge-count-newest-first-list-and-five-character-project-label')
    tap(newest)
    for _ in range(20):
        if contains('받은 세트 · 읽기 전용'):break
        time.sleep(1)
    assert contains('받은 세트 · 읽기 전용') and contains('수신 메모')
    assert find('사진 메모 텍스트') is None and find('사진 촬영') is None
    assert find('메모 텍스트 초기화') is None and find('AI') is None and find('재촬영') is None
    assert not any(n.attrib.get('class')=='android.widget.EditText' for n in tree().iter('node'))
    screenshot('android-received-reader.png');tap('수신함으로 돌아가기')
    assert contains('수신 모드, 새 자료 1개');rpc('receipts');fixture.terminate();fixture.wait(timeout=5)
    verified.append('received-capture-layout-is-read-only-and-opening-one-set-decrements-unread-count')
    adb('shell','am','force-stop','com.hojung1231.bogoagain')
    adb('shell','am','start','-W','-n','com.hojung1231.bogoagain/.MainActivity');time.sleep(4)
    tap('수신함 · 새 자료 1개');assert contains('최신수신프로젝트') and contains('수신 모드, 새 자료 1개')
    verified.append('team-identity-inbox-and-read-state-persist-after-restart')
    assert not diagnostic_old_build,'Diagnostic build 9 still requires cancel-recovery fix in build 10'
finally:
    pathlib.Path('android-ui-verification.json').write_text(json.dumps({'buildCode':build_code,'knownIssueSkipped':['cancel-recovery'] if diagnostic_old_build else [],'verified':verified},ensure_ascii=False,indent=2),encoding='utf-8')
    pathlib.Path('window.xml').write_text(ET.tostring(tree(),encoding='unicode'),encoding='utf-8')
    screenshot('android-final.png')
