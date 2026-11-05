import React,{useRef} from 'react';
import {ScrollView,StyleSheet,Text,View} from 'react-native';
import {useVoice} from './voice';
export default function Transcript(){const voice=useVoice(),scroll=useRef<React.ComponentRef<typeof ScrollView>|null>(null);return <View style={styles.box}><ScrollView ref={scroll} nestedScrollEnabled showsVerticalScrollIndicator={false} onContentSizeChange={()=>scroll.current?.scrollToEnd({animated:true})}><Text accessibilityLabel="실시간 음성 텍스트" style={styles.text}>{voice.text||voice.status||(voice.active?'말씀해 주세요':'음성 메모를 누르면 여기에 실시간 텍스트가 표시됩니다')}</Text></ScrollView></View>;}
const styles=StyleSheet.create({box:{height:58,marginTop:7,marginBottom:3,paddingHorizontal:12,paddingVertical:4,overflow:'hidden'},text:{fontSize:10,lineHeight:16,color:'#708166'}});
