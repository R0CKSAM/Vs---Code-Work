/* Standalone ZIP STORE writer for separate CSV exports. No CDN or dependencies.
 * Inputs are the already sanitized CSV strings from picked-export.mjs.
 * Applies ZIP32 conservative size limits, no duplicate file names. */
const encoder=new TextEncoder();
const table=new Uint32Array(256);
for(let n=0;n<256;n++){let c=n;for(let k=0;k<8;k++)c=(c&1)?0xEDB88320^(c>>>1):c>>>1;table[n]=c>>>0;}
function crc32(data){let crc=0xFFFFFFFF;for(const byte of data)crc=table[(crc^byte)&0xFF]^(crc>>>8);return(crc^0xFFFFFFFF)>>>0;}
const u16=(out,at,n)=>{out[at]=n&255;out[at+1]=(n>>>8)&255;};
const u32=(out,at,n)=>{out[at]=n&255;out[at+1]=(n>>>8)&255;out[at+2]=(n>>>16)&255;out[at+3]=(n>>>24)&255;};
export function buildCsvZip(files){
 if(!Array.isArray(files)||!files.length||files.length>100)throw new Error('Choose between 1 and 100 CSV files.');
 const items=[],seen=new Set();let total=22;
 for(const row of files){
  let name=String(row?.name||'').replace(/[^A-Za-z0-9 _.-]/g,'_').slice(0,85);
  if(!name.toLowerCase().endsWith('.csv'))name+='.csv';
  if(name==='.'||name==='..'||seen.has(name.toLowerCase()))throw new Error('Duplicate or invalid CSV filename.');
  seen.add(name.toLowerCase());
  const bytes=encoder.encode(String(row?.csv??'')),fname=encoder.encode(name);
  if(!fname.length||fname.length>65535||bytes.length>=0xFFFFFFFF)throw new Error('A CSV file exceeds ZIP32 limits.');
  const length=30+fname.length+bytes.length,central=46+fname.length;
  total+=length+central;
  if(total>=0xFFFFFFFF||total>350*1024*1024)throw new Error('Export is too large for a single CSV ZIP. Export fewer dates or groups.');
  items.push({fname,bytes,length,central,crc:crc32(bytes)});
 }
 const out=new Uint8Array(total);let pos=0;let cent=[];
 for(const item of items){
  const start=pos;u32(out,pos,0x04034b50);u16(out,pos+4,20);u16(out,pos+6,0x0800);u16(out,pos+8,0);
  u16(out,pos+10,0);u16(out,pos+12,0x21);u32(out,pos+14,item.crc);u32(out,pos+18,item.bytes.length);u32(out,pos+22,item.bytes.length);
  u16(out,pos+26,item.fname.length);u16(out,pos+28,0);pos+=30;
  out.set(item.fname,pos);pos+=item.fname.length;out.set(item.bytes,pos);pos+=item.bytes.length;
  cent.push({item,start});
 }
 const directoryOffset=pos;
 for(const {item,start} of cent){
  u32(out,pos,0x02014b50);u16(out,pos+4,20);u16(out,pos+6,20);u16(out,pos+8,0x0800);u16(out,pos+10,0);
  u16(out,pos+12,0);u16(out,pos+14,0x21);u32(out,pos+16,item.crc);u32(out,pos+20,item.bytes.length);u32(out,pos+24,item.bytes.length);
  u16(out,pos+28,item.fname.length);u16(out,pos+30,0);u16(out,pos+32,0);u16(out,pos+34,0);u16(out,pos+36,0);
  u32(out,pos+38,0);u32(out,pos+42,start);pos+=46;out.set(item.fname,pos);pos+=item.fname.length;
 }
 const directoryLength=pos-directoryOffset;
 u32(out,pos,0x06054b50);u16(out,pos+4,0);u16(out,pos+6,0);u16(out,pos+8,items.length);u16(out,pos+10,items.length);
 u32(out,pos+12,directoryLength);u32(out,pos+16,directoryOffset);u16(out,pos+20,0);pos+=22;
 if(pos!==out.length)throw new Error('CSV ZIP allocation mismatch.');
 return out;
}
