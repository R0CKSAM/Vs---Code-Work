// Local Flatpickr calendar, using the RevenueLive date-picker pattern.
(()=>{
  const el=id=>document.getElementById(id),picker=el('rangePicker');
  let pending=null,bounds='';
  const iso=date=>calendar.formatDate(date,'Y-m-d');
  const label=value=>new Date(value+'T00:00:00Z').toLocaleDateString('en-GB',{day:'2-digit',month:'short',year:'numeric',timeZone:'UTC'});
  const calendar=flatpickr(el('calendarInput'),{
    inline:true,mode:'range',dateFormat:'Y-m-d',disableMobile:true,
    onChange(dates){
      pending=dates.length?[iso(dates[0]),iso(dates.at(-1))]:null;
      el('applyDateRange').disabled=!pending;
      el('calendarStatus').textContent=pending?`${label(pending[0])} to ${label(pending[1])} · IST`:'Select a start and end date.';
    }
  });
  function position(){
    const box=el('rangeTitle').getBoundingClientRect(),panel=el('rangePanel');
    panel.style.left=Math.max(12,Math.min(box.left,innerWidth-panel.offsetWidth-12))+'px';
    panel.style.top=Math.max(12,Math.min(box.bottom+8,innerHeight-panel.offsetHeight-12))+'px';
  }
  function stage(start,end){
    pending=[start,end];calendar.setDate(pending,false);calendar.jumpToDate(end);
    el('applyDateRange').disabled=false;
    el('calendarStatus').textContent=`${label(start)} to ${label(end)} · IST`;
  }
  window.syncDateRange=()=>{
    const start=el('start').value,end=el('end').value;
    el('rangeText').textContent=start&&end?(start===end?label(start):`${label(start)} – ${label(end)}`):'Date range';
    el('rangeTitle').title=el('rangeText').textContent+' · IST';
    if(typeof meta!=='undefined'&&meta?.dates?.length){
      const nextBounds=meta.dates[0]+'|'+meta.dates.at(-1);
      if(bounds!==nextBounds){calendar.set('minDate',meta.dates[0]);calendar.set('maxDate',meta.dates.at(-1));bounds=nextBounds}
    }
  };
  picker.addEventListener('toggle',()=>{
    if(!picker.open)return;
    pending=null;el('applyDateRange').disabled=true;
    window.syncDateRange();calendar.setDate([el('start').value,el('end').value].filter(Boolean),false);
    if(el('end').value)calendar.jumpToDate(el('end').value);
    el('calendarStatus').textContent='Select a start and end date, or click one day.';
    position();
  });
  el('latestDateRange').onclick=()=>stage(meta.dates.at(-1),meta.dates.at(-1));
  el('allDateRange').onclick=()=>stage(meta.dates[0],meta.dates.at(-1));
  el('weekDateRange').onclick=()=>{
    const end=meta.dates.at(-1),start=new Date(end+'T00:00:00Z');start.setUTCDate(start.getUTCDate()-6);
    stage([start.toISOString().slice(0,10),meta.dates[0]].sort().at(-1),end);
  };
  el('cancelDateRange').onclick=()=>{picker.open=false;el('rangeTitle').focus()};
  el('applyDateRange').onclick=()=>{
    if(!pending)return;
    [el('start').value,el('end').value]=pending;picker.open=false;dirty();el('rangeTitle').focus();apply();
  };
  document.addEventListener('click',e=>{if(picker.open&&!picker.contains(e.target))picker.open=false});
  document.addEventListener('keydown',e=>{
    if(e.key==='Escape'&&picker.open){e.preventDefault();e.stopImmediatePropagation();picker.open=false;el('rangeTitle').focus()}
  },true);
  window.addEventListener('resize',()=>{if(picker.open)position()});
  window.addEventListener('scroll',()=>{if(picker.open)position()},true);
})();
