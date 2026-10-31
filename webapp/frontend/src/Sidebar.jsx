import {BookmarkList} from './Bookmarks.jsx';
import React, {useEffect, useRef, useState} from 'react';

const mainLinks = [
  ['/', '🏔️', 'Dashboard'], ['/case-explorer', '⚖️', 'Case Explorer'],
  ['/opinions', '📜', 'Opinions'], ['/justices', '👩‍⚖️', 'Justices'],
  ['/analysis', '📊', 'Analysis'], ['/oral-arguments', '🎙️', 'Oral Arguments'],
  ['/topics', '📚', 'Topics'], ['/case-orders', '📋', 'Case Orders/3JX'],
  ['/trial-courts', '🏛️', 'Trial Courts'], ['/legal-intelligence', '🔎', 'Legal Intelligence'],
  ['/about', 'ℹ️', 'About'],
];
const profileLinks = [
  ['/attorney-profile', '⚖️', 'Attorney Profile'],
  ['/firm-profile', '🏢', 'Firm Profile'],
];
export default function Sidebar({children,variant='navigation'}) {
  const [open,setOpen]=useState(false);
  const [status,setStatus]=useState(null);
  const trigger=useRef(null), close=useRef(null);
  useEffect(()=>{
    if(variant!=='status')return;
    fetch('/api/site-status').then(r=>{if(!r.ok)throw Error();return r.json();}).then(setStatus).catch(()=>setStatus({has_data:false}));
  },[variant]);
  useEffect(()=>{
    if(!open)return;
    close.current?.focus();
    const onKey = e => {if(e.key==='Escape'){setOpen(false);trigger.current?.focus();}};
    document.addEventListener('keydown',onKey);
    return ()=>document.removeEventListener('keydown',onKey);
  },[open]);
  const links = items => items.map(([href,icon,label])=><a key={href} href={href} className={location.pathname===href ? 'nav-active' : undefined} aria-current={location.pathname===href ? 'page' : undefined}><span aria-hidden="true">{icon}</span> {label}</a>);
  return <><button ref={trigger} type="button" className="sidebar-open" aria-label="Open navigation and filters" aria-expanded={open} aria-controls="site-sidebar" onClick={()=>setOpen(true)}>»</button>{open && <button className="sidebar-backdrop" aria-label="Close navigation" onClick={()=>{setOpen(false);trigger.current?.focus();}}/>}<aside id="site-sidebar" className={`${open?'sidebar-visible':''} ${variant==='status'?'status-sidebar':''}`}><button ref={close} type="button" className="sidebar-close" aria-label="Close navigation" onClick={()=>{setOpen(false);trigger.current?.focus();}}>×</button>{variant==='status' ? <section className="site-status"><hr/><h3>📊 Data Status</h3>{status?.updated && <p className="caption"><b>Last updated:</b> {status.updated}</p>}{status?.has_steps && (status.all_success ? <p className="notice success">✅ ✓ All refresh steps successful</p> : <p className="notice">⚠️ {status.failed_count} step(s) had issues</p>)}{!status?.has_manifest && status && <p className="caption">{status.has_data ? `Data from: ${status.updated}` : 'Status: No data available'}</p>}<p className="caption"><a href="https://www.courts.nh.gov/supreme-court">NH Supreme Court →</a></p></section> : <><div className="nav-heading">Main</div><nav aria-label="Main navigation">{links(mainLinks)}</nav><div className="nav-heading">Profiles</div><nav aria-label="Profiles navigation">{links(profileLinks)}</nav><BookmarkList/>{children}</>}</aside></>;
}
