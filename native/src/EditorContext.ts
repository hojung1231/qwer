import {createContext} from 'react';
import {RecordItem,Annotation} from './model';
export const EditorContext=createContext<{item:RecordItem|null;updateMemo?:(text:string)=>void;onMemoFocus?:()=>void;resetMemo?:()=>void;save:(uri:string,originalUri:string,annotations:Annotation[])=>void}|null>(null);
