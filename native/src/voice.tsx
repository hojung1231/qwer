import {createContext,useContext,useEffect,useRef,useState} from 'react';
import {AppState} from 'react-native';
import {ExpoSpeechRecognitionModule as Speech,useSpeechRecognitionEvent} from 'expo-speech-recognition';
import {keepMedia} from './storage';
export type VoiceResult={target:string|null;text:string;uri?:string};
export function useVoiceSession(onSave:(result:VoiceResult)=>void){
 const [phase,setPhase]=useState<'idle'|'starting'|'recording'|'stopping'>('idle'),[text,setText]=useState(''),[status,setStatus]=useState(''),[seconds,setSeconds]=useState(0);
 const session=useRef<{target:string|null;final:string;partial:string;file:Promise<string|undefined>;done?:()=>void;stopping:boolean}|null>(null),save=useRef(onSave),timer=useRef<ReturnType<typeof setInterval>|undefined>(undefined);useEffect(()=>{save.current=onSave;},[onSave]);
 const stop=async()=>{const s=session.current;if(!s)return;if(s.stopping)return new Promise<void>(resolve=>{const prev=s.done;s.done=()=>{prev?.();resolve();};});s.stopping=true;setPhase('stopping');Speech.stop();return new Promise<void>(resolve=>{s.done=resolve;});};
 useSpeechRecognitionEvent('start',()=>{setPhase('recording');setStatus('음성을 텍스트로 변환 중');});
 useSpeechRecognitionEvent('result',event=>{const s=session.current;if(!s)return;const value=event.results[0]?.transcript||'';if(event.isFinal){s.final=[s.final,value].filter(Boolean).join(' ');s.partial='';}else s.partial=value;setText([s.final,s.partial].filter(Boolean).join(' '));});
 useSpeechRecognitionEvent('audioend',event=>{const s=session.current;if(s&&event.uri)s.file=keepMedia(event.uri,'wav');});
 useSpeechRecognitionEvent('error',event=>{if(event.error!=='aborted'&&event.error!=='no-speech')setStatus('음성 인식을 사용할 수 없습니다. 기기 음성 서비스와 한국어 모델을 확인하세요.');});
 useSpeechRecognitionEvent('end',()=>{const s=session.current;if(!s)return;clearInterval(timer.current);setPhase('stopping');(async()=>{try{const uri=await s.file;const transcript=[s.final,s.partial].filter(Boolean).join(' ').trim();if(uri||transcript)save.current({target:s.target,text:transcript,uri});setText(transcript);setStatus(transcript?'음성 메모를 저장했습니다':'음성 인식 결과가 없습니다');}catch{setStatus('음성 파일 저장 실패 · 텍스트를 확인해 주세요');}finally{session.current=null;setPhase('idle');s.done?.();}})();});
 async function start(target:string|null){if(session.current)return;const permission=await Speech.requestPermissionsAsync();if(!permission.granted)throw Error('마이크와 음성 인식 권한을 허용해 주세요.');if(!Speech.isRecognitionAvailable())throw Error('기기에 사용 가능한 음성 인식 서비스가 없습니다.');setText('');setSeconds(0);setStatus('기기 음성 서비스를 연결하는 중…');setPhase('starting');session.current={target,final:'',partial:'',file:Promise.resolve(undefined),stopping:false};try{Speech.start({lang:'ko-KR',interimResults:true,continuous:true,recordingOptions:{persist:Speech.supportsRecording()},addsPunctuation:true});const started=Date.now();timer.current=setInterval(()=>{const n=Math.floor((Date.now()-started)/1000);setSeconds(n);if(n>=180)stop();},500);}catch(e){session.current=null;setPhase('idle');throw e;}}
 useEffect(()=>{const sub=AppState.addEventListener('change',state=>{if(state!=='active')stop();});return()=>{sub.remove();clearInterval(timer.current);Speech.abort();};},[]);
 return {phase,text,status,seconds,active:phase!=='idle',start,stop};
}
export type VoiceSession=ReturnType<typeof useVoiceSession>;
export const VoiceContext=createContext<VoiceSession|null>(null);
export const useVoice=()=>{const v=useContext(VoiceContext);if(!v)throw Error('음성 세션이 준비되지 않았습니다.');return v;};
