import React, {useEffect, useState} from 'react';
import Plot from './Plot.jsx';
function useData(path) {
  const [data,setData]=useState(null), [error,setError]=useState('');
  useEffect(()=>{const controller=new AbortController();fetch(path,{signal:controller.signal}).then(r=>{if(!r.ok)throw Error('Could not load oral argument statistics');return r.json();}).then(setData).catch(e=>{if(e.name!=='AbortError')setError(e.message);});return()=>controller.abort();},[path]);
  return [data,error];
}
export function Statistics() {
  const [data,error]=useData('/api/arguments/statistics');
  if(error)return <p role="alert" className="error">{error}</p>;
  if(!data)return <p>Loading statistics…</p>;
  const c=data.charts, s=data.speaker_summary;
  if(!c.year)return <p>No oral arguments with confirmed dates are available for statistics.</p>;
  return <><Plot figure={c.year}/><Plot figure={c.month}/><div className="topic-columns"><Plot figure={c.duration}/><Plot figure={c.words}/></div><hr/><h2>Speaking Patterns</h2>{s && <><div className="topic-columns"><Plot figure={c.speaking_time}/><Plot figure={c.speaking_pace}/></div><p className="caption">Based on {s.count.toLocaleString()} arguments. Counsel speaks {s.counsel.toFixed(1)}% of the time on average, Justices {s.justices.toFixed(1)}%.</p></>}<p className="caption">Statistics describe the machine-generated transcript collection. They are not measures of case importance, speaker performance, or transcript accuracy.</p></>;
}
export function Trends() {
  const [data,error]=useData('/api/arguments/trends');
  if(error)return <p role="alert" className="error">{error}</p>;
  if(!data)return <p>Loading trends…</p>;
  if(!data.available)return <><h2>Temporal Trends</h2><p>Analyze how oral arguments have evolved over time.</p><p>Enhanced statistics are not available.</p></>;
  const c=data.charts, rows=Object.entries(data.complexity || {});
  return <><h2>Temporal Trends</h2><p>Analyze how oral arguments have evolved over time.</p><h3>Arguments by Year</h3><div className="topic-columns"><Plot figure={c.yearly}/><Plot figure={c.yearly_duration}/></div><Plot figure={c.growth}/><h3>Seasonal Patterns</h3><div className="topic-columns"><Plot figure={c.monthly}/><Plot figure={c.quarterly}/></div><h3>Case Complexity Analysis</h3><p>Cases categorized by argument duration (quartiles).</p><div className="topic-columns"><Plot figure={c.complexity}/><Plot figure={c.complexity_duration}/></div>{rows.length>0 && <details><summary>View complexity details</summary><p>This table groups cases by how long the oral argument lasted. Simple means shorter arguments, while Very Complex means longer arguments relative to the full collection. The categories are created by splitting the argument lengths into four equal groups.</p><div className="table-wrap"><table><thead><tr>{['Complexity','Cases','Avg Min','Min Min','Max Min','Avg Segments'].map(v=><th key={v}>{v}</th>)}</tr></thead><tbody>{rows.map(([name,row])=><tr key={name}><td>{name}</td>{['count','avg_duration','min_duration','max_duration','avg_segments'].map(key=><td key={key}>{row[key] ?? '—'}</td>)}</tr>)}</tbody></table></div></details>}<h3>Case Types</h3><Plot figure={c.case_types}/><h3>Attorney Networks</h3><Plot figure={c.firms}/>{data.solo_count>0 && <p>{data.solo_count.toLocaleString()} attorneys argue as solo practitioners.</p>}</>;
}
