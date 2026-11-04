import * as Crypto from 'expo-crypto';
export type RecordItem={id:string;type:'image'|'video'|'audio'|'note';uri?:string;audioUri?:string;memo:string;createdAt:string};
export type Project={id:string;title:string;createdAt:string;updatedAt:string;items:RecordItem[];report:string;feedback:string};
export type Settings={provider:'template'|'qwen'|'openai';url:string;model:string;length:number;photos:number};
export const defaults:Settings={provider:'template',url:'',model:'',length:600,photos:6};
export const uid=()=>Crypto.randomUUID();
export function newProject():Project{const now=new Date();return{id:`${now.getFullYear()}${String(now.getMonth()+1).padStart(2,'0')}${String(now.getDate()).padStart(2,'0')}-${uid().slice(0,8)}`,title:'새 외근 기록',createdAt:now.toISOString(),updatedAt:now.toISOString(),items:[],report:'',feedback:''};}
export const clone=<T,>(p:T):T=>JSON.parse(JSON.stringify(p));
export const escapeHtml=(s:string)=>s.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]!));
export const kindLabel={image:'사진',video:'영상',audio:'음성',note:'메모'};
export function templateReport(p:Project){return `${p.title}\n외근 보고서\n\n작성일: ${new Date(p.createdAt).toLocaleDateString('ko-KR')}\n작업 번호: ${p.id}\n\n1. 현장 확인 내용\n${p.items.map((x,i)=>`\n[기록 ${i+1} · ${kindLabel[x.type]}]\n${x.memo.trim()||'확인 내용 입력 필요'}${x.audioUri?'\n음성 메모 첨부':''}`).join('\n')}\n\n2. 후속 조치\n담당자, 조치 내용, 완료 예정일을 확인해 입력하세요.${p.feedback?`\n\n재작성 요청 메모: ${p.feedback}`:''}\n\n※ 기본 양식 초안입니다. 사실관계 확인 후 공유하세요.`;}
export function validateBaseUrl(value:string){let u:URL;try{u=new URL(value);}catch{throw Error('서버 주소를 확인해 주세요.');}if(u.username||u.password||u.search||u.hash)throw Error('서버 기본 주소만 입력하세요.');const host=u.hostname;const privateHost=/^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)/.test(host);if(u.protocol!=='https:'&&!(u.protocol==='http:'&&privateHost))throw Error('HTTPS 또는 사내 IP의 HTTP 주소를 사용하세요.');return u.origin+u.pathname.replace(/\/$/,'');}
