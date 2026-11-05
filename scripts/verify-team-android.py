"""Focused fake-team verification using the same APK and shared gesture helpers."""
import pathlib,json,textwrap
source=pathlib.Path('scripts/verify-android.py').read_text(encoding='utf-8')
exec(source.split('\ntry:\n',1)[0])
try:
    if contains("Pixel Launcher isn't responding"):
        tap('Close app');adb('shell','am','start','-W','-n','com.hojung1231.bogoagain/.MainActivity');time.sleep(3)
    assert contains('새 작업 시작')
    make_fixture()
    path=pathlib.Path('bogo-highres.bogo.json');data=json.loads(path.read_text());data['project']['items'][0]['originalBase64']=data['project']['items'][0]['mediaBase64'];path.write_text(json.dumps(data));adb('push',str(path),'/sdcard/Download/bogo-highres.bogo.json')
    tap('복원');time.sleep(2)
    if find('bogo-highres.bogo.json') is None:tap('Show roots');tap('Downloads')
    tap('bogo-highres.bogo.json');time.sleep(2);tap('OK');tap('HighRes Fixture')
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
    assert contains('받은 초대로 연결');tap('초대한 팀원과 연결');time.sleep(3)
    for _ in range(8):
        if contains('연결 완료'):tap('OK');break
        time.sleep(.5)
    assert contains('BogoPeerTwo');screenshot('android-team.png');tap('닫기')
    verified.append('team-table-manual-name-phone-and-single-use-invitation-connect-fake-peer')
    time.sleep(2)
    if contains('연결 완료'):tap('OK')
    if find('홈') is not None:tap('홈')
    tap('HighRes Fixture');tap('세트 공유');tap('수신자 BogoPeer');tap('수신자 BogoPeerTwo');tap('선택한 2명에게 보내기')
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
    time.sleep(2);received_frame=bounds(find('촬영 프레임'));center=((received_frame[0]+received_frame[2])//2,(received_frame[1]+received_frame[3])//2);gesture('image-loaded',received_frame,center,center)
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
