import React,{useRef} from 'react';
import {Pressable,ScrollView,StyleSheet,Text,TextInput,View} from 'react-native';
import {useVoice} from './voice';
import {Icon} from './ui';
type Props={value?:string;recordId?:string;onChangeText?:(text:string)=>void;onFocus?:()=>void;onReset?:()=>void;disabled?:boolean;readOnly?:boolean};
export default function Transcript({value='',recordId,onChangeText,onFocus,onReset,disabled=false,readOnly=false}:Props){
 const voice=useVoice(),scroll=useRef<React.ComponentRef<typeof ScrollView>|null>(null);
 const live=!readOnly&&voice.active&&(voice.target===recordId||!voice.target&&!recordId);
 const display=live?[value,voice.text].filter(Boolean).join('\n'):value;
 return <View style={styles.box}>{live||readOnly?<ScrollView ref={scroll} nestedScrollEnabled showsVerticalScrollIndicator={false} onContentSizeChange={()=>{if(live)scroll.current?.scrollToEnd({animated:true});}}><Text accessibilityLabel={readOnly?'수신 메모':'실시간 음성 텍스트'} style={styles.text}>{display||(live?voice.status||'말씀해 주세요':'메모 없음')}</Text></ScrollView>:<TextInput accessibilityLabel="사진 메모 텍스트" editable={!disabled} value={value} onFocus={onFocus} onChangeText={onChangeText} multiline scrollEnabled textAlignVertical="top" placeholder="음성 메모를 녹음하거나 여기를 눌러 입력하세요" placeholderTextColor="#82917c" style={[styles.text,styles.input]}/ >}{!readOnly&&<Pressable accessibilityLabel="메모 텍스트 초기화" accessibilityHint="텍스트만 비우고 음성 파일은 보관합니다" disabled={disabled||live||!value} hitSlop={6} style={[styles.clear,(!value||live||disabled)&&{opacity:.25}]} onPress={()=>{if(onReset)onReset();else{onFocus?.();onChangeText?.('');}}}><Icon name="close-circle-outline" size={16} color="#82917c"/></Pressable>}</View>;
}
const styles=StyleSheet.create({box:{height:62,marginTop:7,marginBottom:3,paddingLeft:10,paddingRight:30,paddingVertical:5,borderRadius:9,backgroundColor:'#82917c0c',overflow:'hidden'},text:{fontSize:10,lineHeight:16,color:'#708166'},input:{height:52,padding:0,paddingTop:0,paddingBottom:0},clear:{position:'absolute',right:4,top:5,padding:3}});
