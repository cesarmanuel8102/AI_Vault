import {openSync,closeSync,unlinkSync} from "node:fs";
export interface LeaseRelease {():void;owns():boolean}
export function lock(path:string):LeaseRelease {let fd:number;try{fd=openSync(path,"wx");}catch{throw new Error("operator proxy lock occupied");}let owned=true;const release=(()=>{if(!owned)return;closeSync(fd);owned=false;try{unlinkSync(path);}catch{}}) as LeaseRelease;release.owns=()=>owned;return release;}
