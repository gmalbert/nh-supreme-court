import React, {useEffect, useId, useRef, useState} from 'react';
export default function MultiSelect({label, options, value, onChange}) {
  const id=useId(), [query,setQuery]=useState('');
  const field=useRef(null), dropdown=useRef(null);
  useEffect(()=>{
    const dismiss=e=>{if(dropdown.current?.open && !field.current?.contains(e.target)) dropdown.current.open=false;};
    const escape=e=>{if(e.key==='Escape' && dropdown.current?.open){dropdown.current.open=false; dropdown.current.querySelector('summary')?.focus();}};
    document.addEventListener('pointerdown',dismiss); document.addEventListener('keydown',escape);
    return ()=>{document.removeEventListener('pointerdown',dismiss);document.removeEventListener('keydown',escape);};
  },[]);
  const normalized=options.map(o=>typeof o==='string'?{value:o,label:o}:o);
  const labels=new Map(normalized.map(o=>[String(o.value),o.label]));
  const selected=value.map(String);
  const toggle=v=>onChange(selected.includes(v)?selected.filter(x=>x!==v):[...selected,v]);
  return <div ref={field} className={`multi-field${selected.length>6?' multi-field-overflow':''}`}><div id={id} className="multi-label">{label}</div><div className="multi-control"><div className="multi-tags">{selected.map(v=><span className="multi-tag" key={v}>{labels.get(v) || v}<button type="button" aria-label={`Remove ${labels.get(v) || v}`} onClick={()=>toggle(v)}>×</button></span>)}{!selected.length && <span className="caption">Choose options</span>}</div><details ref={dropdown} className="multi-dropdown"><summary aria-label={`Choose ${label}`}>⌄</summary><div className="multi-menu"><input aria-label={`Search ${label}`} placeholder="Search options" value={query} onChange={e=>setQuery(e.target.value)}/><div className="multi-options">{normalized.filter(o=>String(o.label).toLowerCase().includes(query.toLowerCase())).map(o=><label key={o.value}><input type="checkbox" checked={selected.includes(String(o.value))} onChange={()=>toggle(String(o.value))}/>{o.label}</label>)}</div></div></details>{selected.length>0 && <button type="button" className="multi-clear" aria-label={`Clear ${label}`} onClick={()=>onChange([])}>×</button>}</div></div>;
}
