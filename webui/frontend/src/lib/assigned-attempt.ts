"use client";
import {useEffect,useState} from 'react';
import {getAttempt,type Attempt} from './assessments';
/** URL selects a server-owned identity; it never supplies trusted config. */
export function useAssignedAttempt(){
 const [attempt,setAttempt]=useState<Attempt|null>(null); const [error,setError]=useState('');
 useEffect(()=>{let active=true;const id=new URLSearchParams(window.location.search).get('attempt');if(id)void getAttempt(id).then(a=>{if(active)setAttempt(a);}).catch(e=>{if(active)setError(String(e));});return()=>{active=false;};},[]);
 return {attempt,context:attempt?.assignment_context??null,error};
}
