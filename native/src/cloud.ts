import {AppState} from 'react-native';
import {createClient} from '@supabase/supabase-js';
import * as SecureStore from 'expo-secure-store';
import {File,Directory,Paths} from 'expo-file-system';
import {fetch as expoFetch} from 'expo/fetch';
import {IncomingSet,Project,Settings,TeamMember,uid} from './model';
import {mergeTeam} from './teamCore';
export const CLOUD_URL='https://zhiqrtjhwcnaozlkmknh.supabase.co';
export const CLOUD_KEY='sb_publishable_MipgJbaS4uy3NRcKb-CZ6A_QqR_WDmz';
let writes=Promise.resolve();
const authStorage={
 async getItem(key:string){await writes;const meta=await SecureStore.getItemAsync(key);if(!meta)return null;const {generation,count}=JSON.parse(meta);let value='';for(let n=0;n<count;n++)value+=await SecureStore.getItemAsync(`${key}.${generation}.${n}`)||'';return value||null;},
 async setItem(key:string,value:string){writes=writes.catch(()=>{}).then(async()=>{const old=await SecureStore.getItemAsync(key),generation=uid(),count=Math.ceil(value.length/1800);for(let n=0;n<count;n++)await SecureStore.setItemAsync(`${key}.${generation}.${n}`,value.slice(n*1800,(n+1)*1800));await SecureStore.setItemAsync(key,JSON.stringify({generation,count}));if(old){const prior=JSON.parse(old);for(let n=0;n<prior.count;n++)await SecureStore.deleteItemAsync(`${key}.${prior.generation}.${n}`);}});await writes;},
 async removeItem(key:string){writes=writes.catch(()=>{}).then(async()=>{const old=await SecureStore.getItemAsync(key);await SecureStore.deleteItemAsync(key);if(old){const prior=JSON.parse(old);for(let n=0;n<prior.count;n++)await SecureStore.deleteItemAsync(`${key}.${prior.generation}.${n}`);}});await writes;}
};
export const cloud=createClient(CLOUD_URL,CLOUD_KEY,{auth:{storage:authStorage,persistSession:true,autoRefreshToken:true,detectSessionInUrl:false}});
AppState.addEventListener('change',state=>{if(state==='active')cloud.auth.startAutoRefresh();else cloud.auth.stopAutoRefresh();});
let signing:Promise<string>|undefined;
export async function cloudUser(){if(!signing)signing=(async()=>{const {data,error}=await cloud.auth.getSession();if(error)throw error;if(data.session)return data.session.user.id;const result=await cloud.auth.signInAnonymously();if(result.error)throw Error('팀 송수신 서버에 연결하지 못했습니다. 잠시 후 다시 시도하세요.');if(!result.data.user)throw Error('기기 연결 정보를 받지 못했습니다.');return result.data.user.id;})().finally(()=>{signing=undefined;});return signing;}
export async function saveCloudProfile(settings:Settings){const name=settings.myName?.trim();if(!name)throw Error('팀원 등록에서 내 이름을 먼저 입력해 주세요.');const id=await cloudUser();const {error}=await cloud.from('bogo_profiles').upsert({id,name,phone:settings.myPhone?.trim()||''});if(error)throw error;return id;}
export async function refreshTeam(local:TeamMember[]|(()=>TeamMember[])){const id=await cloudUser();const links=await cloud.from('bogo_links').select('peer').eq('owner',id);if(links.error)throw links.error;const peers=links.data?.length?await cloud.from('bogo_profiles').select('id,name,phone').in('id',links.data.map(l=>l.peer)):{data:[],error:null};if(peers.error)throw peers.error;const claims=await cloud.from('bogo_invites').select('token,claimed_by').eq('owner',id).not('claimed_by','is',null);if(claims.error)throw claims.error;return mergeTeam(typeof local==='function'?local():local,peers.data||[],claims.data||[]);}
export async function createInvite(settings:Settings){const id=await saveCloudProfile(settings);const {data,error}=await cloud.from('bogo_invites').insert({owner:id}).select('token').single();if(error)throw error;return data.token as string;}
export async function acceptInvite(token:string,settings:Settings){await saveCloudProfile(settings);const {error}=await cloud.rpc('bogo_accept_invite',{invite_token:token});if(error)throw Error('초대가 만료되었거나 이미 사용됐습니다. 새 초대 링크를 요청해 주세요.');}
export async function inboxSummaries():Promise<IncomingSet[]>{const id=await cloudUser(),rows:IncomingSet[]=[];for(let offset=0;;offset+=500){const {data,error}=await cloud.from('bogo_deliveries').select('id,set_id,sender,created_at,read_at,bogo_sets!bogo_delivery_set_sender(project_name,sender_name,photo_count,item_count,ready)').eq('recipient',id).order('created_at',{ascending:false}).order('id',{ascending:false}).range(offset,offset+499);if(error)throw error;for(const row of data||[]){const set=row.bogo_sets as unknown as {project_name:string;sender_name:string;photo_count:number;item_count:number;ready:boolean};if(set?.ready)rows.push({id:row.id,setId:row.set_id,senderId:row.sender,senderName:set.sender_name,projectName:set.project_name,photoCount:set.photo_count,itemCount:set.item_count,createdAt:row.created_at,readAt:row.read_at||undefined});}if(!data||data.length<500)break;}return rows;}
export async function markRead(id:string,at:string){const {error}=await cloud.from('bogo_deliveries').update({read_at:at}).eq('id',id);if(error)throw error;}
async function headers(){await cloudUser();const {data,error}=await cloud.auth.getSession();if(error||!data.session)throw Error('팀 송수신 연결을 확인해 주세요.');return {apikey:CLOUD_KEY,Authorization:`Bearer ${data.session.access_token}`};}
const objectUrl=(path:string)=>`${CLOUD_URL}/storage/v1/object/bogo-sets/${path.split('/').map(encodeURIComponent).join('/')}`;
export async function sendSet(project:Project,projectName:string,settings:Settings,recipients:TeamMember[],progress:(text:string)=>void){
 const targets=[...new Set(recipients.map(m=>m.remoteId).filter((id):id is string=>!!id))];if(!targets.length)throw Error('초대 연결을 마친 팀원을 선택해 주세요.');
 const sender=await saveCloudProfile(settings),id=uid(),prefix=`${sender}/${id}`,files:{path:string;file:File;mime:string}[]=[],items=[];
 let bytes=0;
 for(const item of project.items){const row={...item};for(const field of ['uri','originalUri','audioUri'] as const){const uri=item[field];if(!uri)continue;const ext=field==='audioUri'?(uri.toLowerCase().endsWith('.wav')?'wav':'m4a'):item.type==='video'&&field==='uri'?'mp4':'jpg',file=new File(uri);if(file.size>50*1024*1024)throw Error('세트 안의 개별 파일은 50MB 이하여야 합니다.');bytes+=file.size;const name=`${uid()}.${ext}`;row[field]=name;files.push({path:`${prefix}/${name}`,file,mime:ext==='jpg'?'image/jpeg':ext==='mp4'?'video/mp4':ext==='wav'?'audio/wav':'audio/mp4'});}items.push(row);}
 if(bytes>200*1024*1024)throw Error('세트 공유는 한 번에 200MB까지 가능합니다.');
 const inserted=await cloud.from('bogo_sets').insert({id,sender,project_name:projectName.slice(0,100),sender_name:settings.myName!.trim(),photo_count:items.filter(i=>i.type==='image').length,item_count:items.length});if(inserted.error)throw inserted.error;
 const auth=await headers();let done=0;
 for(const entry of files){progress(`자료 업로드 ${++done}/${files.length}`);const response=await expoFetch(objectUrl(entry.path),{method:'POST',headers:{...await headers(),'Content-Type':entry.mime},body:entry.file,signal:AbortSignal.timeout(180000)});if(!response.ok)throw Error(`자료 업로드 실패 (${response.status}). 다시 시도해 주세요.`);}
 const manifest={format:'bogo-set-v1',project:{...project,folder:undefined,projectFolderId:undefined,items}};
 const result=await expoFetch(objectUrl(`${prefix}/manifest.json`),{method:'POST',headers:{...auth,'Content-Type':'application/json'},body:JSON.stringify(manifest),signal:AbortSignal.timeout(30000)});if(!result.ok)throw Error('세트 정보 업로드에 실패했습니다.');
 const ready=await cloud.from('bogo_sets').update({ready:true}).eq('id',id);if(ready.error)throw ready.error;
 progress('선택한 팀원에게 전달 중…');const deliveries=targets.map(recipient=>({id:uid(),set_id:id,sender,recipient}));const sent=await cloud.from('bogo_deliveries').insert(deliveries);if(sent.error){const check=await cloud.from('bogo_deliveries').select('recipient').eq('set_id',id);if(check.error||targets.some(target=>!check.data?.some(d=>d.recipient===target)))throw sent.error;}
 return targets.length;
}
export async function downloadSet(row:IncomingSet,progress:(text:string)=>void):Promise<Project>{
 const prefix=`${row.senderId}/${row.setId}`,auth=await headers();const response=await expoFetch(objectUrl(`${prefix}/manifest.json`),{headers:auth,signal:AbortSignal.timeout(30000)});if(!response.ok)throw Error('자료를 읽을 수 없습니다. 연결을 확인하고 다시 시도하세요.');
 const body=await response.text();if(body.length>2*1024*1024)throw Error('세트 정보가 너무 큽니다.');const data=JSON.parse(body);if(data.format!=='bogo-set-v1'||!Array.isArray(data.project?.items)||data.project.items.length>500)throw Error('지원하지 않는 세트 형식입니다.');
 const dir=new Directory(Paths.document,'received',row.setId);dir.create({intermediates:true,idempotent:true});let count=0,total=0;
 const items=[];
 for(const raw of data.project.items){if(!['image','video','audio','note'].includes(raw.type))throw Error('자료 형식 오류');const item={...raw,memo:String(raw.memo||''),id:String(raw.id||uid())};for(const field of ['uri','originalUri','audioUri'] as const){const name=raw[field];if(!name){delete item[field];continue;}if(typeof name!=='string'||!/^[-a-f0-9]+\.(jpg|mp4|wav|m4a)$/.test(name))throw Error('자료 경로 형식 오류');progress(`자료 받는 중 ${++count}`);const destination=new File(dir,name);if(!destination.exists){const temporary=new File(dir,`${name}.${uid()}.part`);let completed=false;try{await File.downloadFileAsync(objectUrl(`${prefix}/${name}`),temporary,{headers:auth});await temporary.move(destination);completed=true;}finally{if(!completed){if(temporary.exists)temporary.delete();if(destination.exists)destination.delete();}}}total+=destination.size;if(total>200*1024*1024)throw Error('200MB를 넘는 세트입니다.');item[field]=destination.uri;}items.push(item);}
 return {id:row.setId,title:String(data.project.title||row.projectName),createdAt:String(data.project.createdAt||row.createdAt),updatedAt:row.createdAt,items,report:String(data.project.report||''),feedback:''};
}
