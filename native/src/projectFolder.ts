import {Directory,File,FileMode} from 'expo-file-system';
import {FolderState,Project,ProjectFolder,Settings,uid} from './model';
export async function chooseProjectRoot(initialUri?:string){
 const directory=await Directory.pickDirectoryAsync(initialUri||'content://com.android.externalstorage.documents/document/primary%3ADocuments');
 return {storageFolderUri:directory.uri,storageFolderName:directory.name};
}
export async function prepareProjectStorage(settings:Settings):Promise<Settings>{
 if(!settings.storageFolderUri)return settings;
 const base=new Directory(settings.storageFolderUri);
 const root=base.name==='보고또보고'?base:(base.list().find(entry=>entry instanceof Directory&&entry.name==='보고또보고') as Directory|undefined)||base.createDirectory('보고또보고');
 const entries=root.list().filter((entry):entry is Directory=>entry instanceof Directory);
 const prior=settings.appFolderBaseUri===settings.storageFolderUri?settings.projectFolders||[]:[];
 const present=new Map(entries.map(entry=>[entry.uri,entry]));
 const folders:ProjectFolder[]=prior.filter(folder=>present.has(folder.uri)).map(folder=>({...folder,name:present.get(folder.uri)!.name}));
 for(const entry of entries.sort((a,b)=>a.name.localeCompare(b.name,'ko-KR',{numeric:true}))){if(!folders.some(folder=>folder.uri===entry.uri))folders.push({id:uid(),name:entry.name,uri:entry.uri,createdAt:new Date().toISOString()});}
 return {...settings,appFolderUri:root.uri,appFolderBaseUri:settings.storageFolderUri,projectFolders:folders,currentProjectFolderId:folders.some(f=>f.id===settings.currentProjectFolderId)?settings.currentProjectFolderId:folders[0]?.id};
}
export function createProjectFolder(settings:Settings,name:string):ProjectFolder{
 const clean=name.trim();
 if(!clean||clean.length>50||clean==='.'||clean==='..'||/[<>:"/\\|?*\u0000-\u001f]/.test(clean))throw Error('프로젝트 이름은 1~50자로 입력하고 경로 기호는 빼 주세요.');
 if(!settings.appFolderUri)throw Error('앱 자료 폴더를 먼저 지정해 주세요.');
 if(settings.projectFolders?.some(folder=>folder.name.toLocaleLowerCase()===clean.toLocaleLowerCase()))throw Error('같은 이름의 프로젝트가 이미 있습니다.');
 const directory=new Directory(settings.appFolderUri).createDirectory(clean);
 return {id:uid(),name:directory.name,uri:directory.uri,createdAt:new Date().toISOString()};
}
export async function exportProjectFolder(project:Project,rootUri:string):Promise<FolderState>{
 const root=new Directory(rootUri);
 const name=`${project.title.replace(/[<>:"/\\|?*\u0000-\u001f]/g,'_').trim().slice(0,50)||'외근 기록'}_${project.id}`;
 let directory:Directory;
 if(project.folder?.rootUri===rootUri)directory=new Directory(project.folder.uri);
 else directory=(root.list().find(entry=>entry instanceof Directory&&entry.name===name) as Directory|undefined)||root.createDirectory(name);
 const files:Record<string,string>={},existing=new Map(directory.list().filter((entry):entry is File=>entry instanceof File).map(file=>[file.name,file]));
 const target=(filename:string,mime:string)=>existing.get(filename)||directory.createFile(filename,mime);
 async function copy(uri:string|undefined,filename:string,mime:string){
  if(!uri)return undefined;
  if(project.folder?.uri!==directory.uri||project.folder.files[filename]!==uri||!existing.has(filename)){
   const input=new File(uri).open(FileMode.ReadOnly);
   try{
    const output=target(filename,mime).open(FileMode.Truncate);
    try{for(;;){const bytes=await input.readBytes(512*1024);if(!bytes.length)break;await output.writeBytes(bytes);}}
    finally{output.close();}
   }finally{input.close();}
  }
  files[filename]=uri;return filename;
 }
 const records=[];
 for(const item of project.items){
  const prefix=`기록_${item.id}`;
  const media=await copy(item.uri,`${prefix}.${item.type==='video'?'mp4':'jpg'}`,item.type==='video'?'video/mp4':'image/jpeg');
  const original=await copy(item.originalUri,`${prefix}_원본.jpg`,'image/jpeg');
  const ext=item.audioUri?.toLowerCase().endsWith('.wav')?'wav':'m4a';
  const audio=await copy(item.audioUri,`${prefix}.${ext}`,ext==='wav'?'audio/wav':'audio/mp4');
  target(`${prefix}.txt`,'text/plain').write(item.memo);
  records.push({...item,uri:media,originalUri:original,audioUri:audio});
 }
 target('보고서.txt','text/plain').write(project.report);
 target('프로젝트.json','application/json').write(JSON.stringify({format:'bogo-project-folder-v1',project:{...project,folder:undefined,items:records}},null,2));
 return {rootUri,uri:directory.uri,name:directory.name,files};
}
