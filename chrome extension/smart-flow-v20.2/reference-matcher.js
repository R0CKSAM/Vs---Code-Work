// Local catalog: filenames and verified character labels, never guessed identities.
globalThis.SmartFlowReferenceMatcher=(()=>{
 const normalize=s=>String(s||'').toLowerCase().replace(/\s*\(\d+\)(?=\.(?:png|jpe?g|webp)\b)/gi,'').replace(/[^a-z0-9]+/g,' ').trim();
 const known={
  'CHAR_ANAYA.png':['Anaya'], 'CHAR_ARJUN.png':['Arjun'], 'CHAR_MEHAK.png':['Mehak'],
  'CHAR_TRISHA.png':['Trisha'], 'CHAR_VEER.png':['Veer'],
  'CAST_SUPPORT.png':['supporting cast','Kavita',"Anaya's mother",'mother of Anaya','Rhea',"Anaya's friend",'Dev',"Arjun's brother",'Aarav',"Mehak's brother",'Nandini',"Mehak's mother","Aarav's mother",'Mahendra',"Veer's father","Trisha's mother",'festival coordinator'],
  'LOC_FESTIVAL.png':['festival location','festival grounds','courtyard approach','main stage','ground level rehearsal','side railing','technical route','coordination desk'],
  'LOC_REHEARSAL_ROOM.png':['rehearsal room'], 'LOC_ANAYA_HOME.png':["Anaya's bedroom",'Anaya home'],
  'LOC_ARJUN_HOME.png':["Arjun's practice room",'Arjun home'], 'LOC_MEHAK_HOME.png':['Mehak home'],
  'LOC_TRISHA_HOME.png':['Trisha home'], 'LOC_WORKSHOP.png':['workshop'],
  'PROP_BOARD.png':['prop board','instrument board','instrument reference','guitar','harp','tabla','drums','microphone']
 };
 function catalog(filenames,custom){
  const names=new Set(filenames),entries=new Map();
  for(const name of names){
   if(!/^[\w -]+\.(png|jpe?g|webp)$/i.test(name))throw Error('Invalid reference filename: '+name);
   entries.set(name,{file:name,aliases:[name,name.replace(/\.(png|jpe?g|webp)$/i,'').replace(/^(CHAR|LOC|REF|CAST)_/i,'').replace(/_/g,' '),...(known[name]||[])]});
  }
  if(custom){
   if(custom.version!==1||!Array.isArray(custom.entries))throw Error('Reference_Catalog.json must use version 1 and an entries array.');
   for(const entry of custom.entries){
    if(!names.has(entry.file)||!Array.isArray(entry.aliases)||entry.aliases.some(a=>typeof a!=='string'||!normalize(a)))throw Error('Invalid catalog entry: '+entry.file);
    entries.get(entry.file).aliases.push(...entry.aliases);
   }
  }
  return {version:1,entries:[...entries.values()],unmapped:[{name:'Stagehand',aliases:['stagehand']},{name:'Young Volunteer',aliases:['young volunteer','volunteer']}]};
 }
 function resolve(text,data){
  const hay=' '+normalize(text)+' ',matches=[];
  for(const entry of data?.entries||[])for(const alias of entry.aliases){
   const needle=' '+normalize(alias)+' ';let at=0;
   while((at=hay.indexOf(needle,at))>=0){matches.push({file:entry.file,at,end:at+needle.length});at++;}
  }
  const files=[...new Set(matches.filter(m=>!matches.some(other=>other.at<=m.at&&other.end>=m.end&&other.end-other.at>m.end-m.at)).map(m=>m.file))];
  const missing=(data?.unmapped||[]).filter(entry=>entry.aliases.some(a=>hay.includes(' '+normalize(a)+' '))&&!files.some(file=>(data.entries.find(e=>e.file===file)?.aliases||[]).some(a=>entry.aliases.some(b=>normalize(a)===normalize(b))))).map(e=>e.name);
  const raw=String(text).toLowerCase();
  for(const match of String(text).matchAll(/[\w-]+\.(?:png|jpe?g|webp)\b/gi)){
   const covered=(data?.entries||[]).some(e=>{const name=e.file.toLowerCase();let at=0;while((at=raw.indexOf(name,at))>=0){if(at<=match.index&&at+name.length>=match.index+match[0].length)return true;at++;}return false;});
   if(!covered)missing.push(match[0]);
  }
  return {files,missing:[...new Set(missing)]};
 }
 function request(text,data){
  // Limit matching to what is requested, excluding "I already have ..." clauses.
  const asked=String(text||'').split(/\b(?:I already have|I have already|already attached|already supplied)\b/i)[0];
  if(!(/\b(?:references?|images?|pictures?|sheets?|boards?)\b/i.test(asked)||/[\w-]+\.(?:png|jpe?g|webp)\b/i.test(asked))||! /\b(?:attach|upload|provide|send|share|need|missing|required)\b/i.test(asked))return null;
  return {...resolve(asked,data),text:asked.slice(0,1200)};
 }
 function castFiles(prompt,data){
  const cast=/CURRENT VISIBLE CAST\s*\/\s*CROP:\s*([^\n\r]+)/i.exec(prompt)?.[1]||'';
  return resolve(cast,data).files;
 }
 return {catalog,resolve,request,castFiles};
})();
