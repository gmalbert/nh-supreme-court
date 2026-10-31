import MultiSelect from './MultiSelect.jsx';
import Sidebar from './Sidebar.jsx';
import React, {useEffect,useMemo,useState} from 'react';
import Plot from './Plot.jsx';
const outcomes = ['Affirmed','Remanded','Affirmed & Remanded','Reversed & Remanded','Reversed','Vacated','Dismissed'];
function Breakdown({rows,fields,rate=false}) {
 const columns=rate?[...fields,'Total','Affirmed','Reversed','Reversed & Remanded','Remanded','Vacated','Dismissed','Affirm %','Reversal %']:[...fields,...outcomes,'Total'];
 const [sort,setSort]=useState(''),[ascending,setAscending]=useState(true);
 const sortedRows=useMemo(()=>{
  if(!rows.length||!sort)return rows;
  return [...rows].sort((a,b)=>{
   const av=a[sort],bv=b[sort];
   if(av==null||av==='')return bv==null||bv==''?0:1;
   if(bv==null||bv==='')return -1;
   const an=Number(String(av).replace(/%$/,'')),bn=Number(String(bv).replace(/%$/,''));
   const numeric=Number.isFinite(an)&&Number.isFinite(bn);
   const cmp=numeric?an-bn:String(av).localeCompare(String(bv),undefined,{numeric:true,sensitivity:'base'});
   return ascending?cmp:-cmp;
  });
 },[rows,sort,ascending]);
 function sortBy(key){if(sort===key)setAscending(value=>!value);else{setSort(key);setAscending(true);}}
 if(!rows.length)return <p>No data available for the selected period.</p>;
 return <div className="table-wrap"><table><thead><tr>{columns.map(v=><th key={v} aria-sort={sort===v?(ascending?'ascending':'descending'):'none'}><button type="button" className="table-sort" onClick={()=>sortBy(v)}>{v.replace('court_type','Court Type').replace('court_base','Court').replace('judge','Trial Judge')}{sort===v?(ascending?' ▲':' ▼'):''}</button></th>)}</tr></thead><tbody>{sortedRows.map((row,i)=><tr key={i}>{columns.map(key=><td key={key}>{rate && key.endsWith('%') ? `${Number(row[key] ?? 0).toFixed(1)}%` : row[key] ?? 0}</td>)}</tr>)}</tbody></table></div>;
}
export default function TrialCourts(){
 const [years,setYears]=useState(()=>Array.from({length:new Date().getFullYear()-1999},(_,i)=>String(2000+i))),[minimum,setMinimum]=useState(3),[data,setData]=useState(null),[error,setError]=useState('');
 const params=useMemo(()=>{const p=new URLSearchParams({min_cases:minimum});years.forEach(y=>p.append('year',y));return p;},[years,minimum]);
 useEffect(()=>{const controller=new AbortController();fetch(`/api/trial-courts?${params}`,{signal:controller.signal}).then(r=>{if(!r.ok)throw Error('Could not load trial court data');return r.json();}).then(v=>{setData(v);setError('');}).catch(e=>{if(e.name!=='AbortError')setError(e.message);});return()=>controller.abort();},[params]);
 return <div className="layout"><Sidebar><hr/><h2>Filters</h2><MultiSelect label="Year(s)" options={Array.from({length:new Date().getFullYear()-1999},(_,i)=>String(2000+i))} value={years} onChange={setYears}/><label>Min cases to show<input type="range" min="2" max="10" value={minimum} onChange={e=>setMinimum(e.target.value)}/> {minimum}</label><img className="sidebar-logo" src="/logo.png" alt="Granite State Appeals"/><p className="caption">Last updated: {data?.updated}</p><a className="download" href={`/api/trial-courts.csv?${params}`}>⬇ Download Filtered CSV</a></Sidebar><main className="trial-courts-page"><h1>Trial Courts</h1><p className="caption">How the NH Supreme Court rules on appeals from each lower court and judge</p>{error && <p className="error" role="alert">{error}</p>}{data && <><div className="oa-metrics">{[['Cases with Court Data',data.total],['Affirmance Rate',`${Math.round(data.affirm_rate)}%`],['Affirmed',data.affirmed],["Reversed / Rev'd & Remanded",data.reversed]].map(([name,v])=><div key={name}><span>{name}</span><strong>{v}</strong></div>)}</div><hr/><h2>Outcomes by Court Type</h2>{data.charts.court_types ? <Plot figure={data.charts.court_types}/> : <p>Not enough data for selected filters.</p>}<details><summary>Individual court breakdown by type</summary><Breakdown rows={data.individual_courts} fields={['court_type','court_base']}/></details><h2>Outcomes by Court</h2><p className="caption">Circuit Court divisions are grouped together. Courts with at least {minimum} cases shown.</p><Plot figure={data.charts.court_groups}/><details><summary>Individual Circuit Court breakdown</summary><Breakdown rows={data.circuit_courts} fields={['court_base']}/></details><hr/><h2>Outcomes by Trial Judge</h2><p className="caption">Judges with at least {minimum} cases in selected period (judge name from lower court record)</p>{data.charts.judges ? <Plot figure={data.charts.judges}/> : <p>Not enough judge data for selected filters.</p>}<hr/><h2>Affirmance &amp; Reversal Rates by Judge</h2><Breakdown rows={data.judges} fields={['judge']} rate/></>}<footer><b>Part of <a href="http://www.gavel-glimpse.com">Gavel Glimpse</a></b><p>This public legal-data site is created for informational and research purposes only. It does not provide legal advice and is not a substitute for consulting a qualified attorney.</p></footer></main></div>;
}
