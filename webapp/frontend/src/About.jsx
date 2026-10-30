import Sidebar from './Sidebar.jsx';
import React, {useEffect, useMemo, useState} from 'react';

const role = value => (value || '').replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase());
function Roster({rows, retired = false}) {
  const fields = retired ? [['display_name','Justice'],['role','Role'],['appointed_by','Appointed By'],['date_appointed','Year Appointed'],['date_retired','Year Retired']] : [['display_name','Justice'],['role','Role'],['appointed_by','Appointed By'],['date_appointed','Date Appointed'],['political_affiliation','Appointing Gov. Party']];
  const [sort,setSort]=useState(''),[ascending,setAscending]=useState(true);
  const sortedRows=useMemo(()=>{
    if(!sort)return rows;
    return [...rows].sort((a,b)=>{
      const av=a[sort],bv=b[sort];
      if(av==null||av==='')return bv==null||bv===''?0:1;
      if(bv==null||bv==='')return -1;
      const cmp=String(av).localeCompare(String(bv),undefined,{numeric:true,sensitivity:'base'});
      return ascending?cmp:-cmp;
    });
  },[rows,sort,ascending]);
  function sortBy(key){if(sort===key)setAscending(value=>!value);else{setSort(key);setAscending(true);}}
  return <div className="table-wrap"><table><thead><tr>{fields.map(([key,label]) => <th key={label} aria-sort={sort===key?(ascending?'ascending':'descending'):'none'}><button type="button" className="table-sort" onClick={()=>sortBy(key)}>{label}{sort===key?(ascending?' ▲':' ▼'):''}</button></th>)}</tr></thead><tbody>{sortedRows.map((row,i) => <tr key={row.key || i}>{fields.map(([key]) => <td key={key}>{key === 'role' ? role(row[key]) : retired && key.startsWith('date_') ? (row[key] || '—').slice(0,4) : row[key] || '—'}</td>)}</tr>)}</tbody></table></div>;
}
export default function About() {
  const [data,setData]=useState(null), [error,setError]=useState('');
  useEffect(()=>{fetch('/api/about').then(r=>{if(!r.ok)throw Error('Could not load dataset statistics');return r.json();}).then(setData).catch(e=>setError(e.message));},[]);
  return <div className="layout"><Sidebar><img className="sidebar-logo" src="/logo.png" alt="Granite State Appeals"/><p className="caption">Last updated: {data?.updated}</p></Sidebar><main className="about-page"><h1>About Granite State Appeals</h1><p className="caption">NH Supreme Court Analytics</p><h2>What is Granite State Appeals?</h2><p><b>Granite State Appeals</b> is an open-source data analytics platform for exploring the opinions and orders of the New Hampshire Supreme Court. It parses and structures the court's published PDFs to make the court's work searchable, analyzable, and accessible.</p><blockquote><b>Not legal advice.</b> This tool is for research, journalism, and public interest purposes only.</blockquote><hr/><h2>Methodology</h2><h3>Vote Parsing</h3><p>The concurrence/dissent block at the end of each opinion is parsed using regular expressions to identify each justice's vote (majority, dissent, concurred separately, not participating).</p><h3>Topic Tagging</h3><p>Topics are assigned using keyword matching against a curated taxonomy of legal topic keywords. Assignments are approximate — complex cases touching multiple areas may not be fully captured.</p><h3>Known Limitations</h3><ul><li>PDFs with unusual formatting may parse partially or incorrectly</li><li>Per curiam opinions have no single author</li><li>Justice roster changes (retirements, appointments) require manual updates</li><li>Case orders receive simpler parsing than full opinions</li></ul><hr/><h3>Current Justice Roster</h3>{error && <p className="error" role="alert">{error}</p>}{data && <><Roster rows={data.justices.filter(j=>j.is_active)}/><details><summary>Retired Justices</summary><Roster retired rows={data.justices.filter(j=>!j.is_active)}/></details><hr/><h3>Dataset Statistics</h3><div className="oa-metrics">{[['Total Opinions',data.total.toLocaleString()],['Years Covered',`${data.year_min}–${data.year_max}`],['Last Updated',data.updated]].map(([k,v])=><div key={k}><span>{k}</span><strong>{v}</strong></div>)}</div></>}<hr/><p><i>Granite State Appeals is not affiliated with the New Hampshire Judicial Branch or any government entity.</i></p><footer><b>Part of <a href="http://www.gavel-glimpse.com">Gavel Glimpse</a></b><p>This public legal-data site is created for informational and research purposes only. It does not provide legal advice and is not a substitute for consulting a qualified attorney.</p></footer></main></div>;
}
