import {requireNativeModule} from 'expo-modules-core';
import type {Annotation} from './model';
export function renderPhoto(source:string,shapes:Annotation[],previewWidth:number):Promise<string>{
 return requireNativeModule('BogoImage').render(source,JSON.stringify(shapes),previewWidth);
}
