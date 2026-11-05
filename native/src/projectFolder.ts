import {Directory,File} from 'expo-file-system';
import type {FolderState,Project} from './model';
export async function chooseProjectRoot(initialUri?:string){
 const directory=await Directory.pickDirectoryAsync(initialUri);
 return {storageFolderUri:directory.uri,storageFolderName:directory.name};
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
  if(project.folder?.uri!==directory.uri||project.folder.files[filename]!==uri||!existing.has(filename))await new File(uri).copy(target(filename,mime),{overwrite:true});
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
