import {createContext} from 'react';
import {RecordItem,Annotation} from './model';
export const EditorContext=createContext<{item:RecordItem|null;save:(uri:string,originalUri:string,annotations:Annotation[])=>void}|null>(null);
