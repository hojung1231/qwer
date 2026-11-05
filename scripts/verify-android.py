"""Android emulator UI verification against the freshly built APK."""
import json, pathlib, re, subprocess, time, xml.etree.ElementTree as ET

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
    for _ in range(6):
        node=find(label)
        if node is not None:
            x1,y1,x2,y2=bounds(node);adb('shell','input','tap',(x1+x2)//2,(y1+y2)//2);time.sleep(1);return
        time.sleep(.5)
    raise AssertionError('Missing UI: '+label)

def screenshot(name):
    pathlib.Path(name).write_bytes(subprocess.check_output(['adb','exec-out','screencap','-p']))

def contains(text):
    return any(text in (n.attrib.get('text','')+' '+n.attrib.get('content-desc','')) for n in tree().iter('node'))

verified=[]
try:
    assert contains('새 작업 시작')
    assert contains('앱 업데이트')
    screenshot('android-home.png');verified.append('home-and-update-button')
    tap('새 작업 시작')
    assert contains('4:3')
    tap('촬영 비율 회전');assert contains('3:4')
    tap('촬영 비율 회전');assert contains('4:3')
    assert not contains('이어서 촬영')
    screenshot('android-capture.png');verified.append('capture-4x3-rotation')
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
finally:
    pathlib.Path('android-ui-verification.json').write_text(json.dumps({'verified':verified},ensure_ascii=False,indent=2),encoding='utf-8')
    pathlib.Path('window.xml').write_text(ET.tostring(tree(),encoding='unicode'),encoding='utf-8')
    screenshot('android-final.png')
