import Plot from './Plot.jsx';
import Sidebar from './Sidebar.jsx';
import React, {useEffect, useMemo, useState} from 'react';

const link = id => `/case-explorer?case=${encodeURIComponent(id)}`;
const title = value => String(value || '').replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase());

export default function CaseExplorer() {
  const [options,setOptions] = useState(null), [year,setYear] = useState(''), [id,setId] = useState('');
  const [detail,setDetail] = useState(null), [error,setError] = useState('');
  useEffect(() => {
    fetch('/api/case-options').then(r => { if (!r.ok) throw Error('Could not load case options'); return r.json(); }).then(data => {
      setOptions(data); const requested = new URLSearchParams(location.search).get('case');
      const found = data.items.find(row => String(row.case_number) === requested);
      const years = data.items.map(row => Number(row.term_year)).filter(Number.isFinite);
      const defaultYear = String(found?.term_year || Math.max(...years));
      setYear(defaultYear);
      if (requested && !found) { setError(`Case ${requested} was not found.`); setId(''); }
      else setId(found?.case_number || data.items.find(row => String(row.term_year) === defaultYear)?.case_number || '');
    }).catch(e => setError(e.message));
  }, []);
  useEffect(() => {
    if (!options) return;
    const restore = () => {
      const requested = new URLSearchParams(location.search).get('case');
      const found = options.items.find(row => String(row.case_number) === requested);
      if (found) { setYear(String(found.term_year)); setId(found.case_number); }
      else if (requested) { setId(''); setDetail(null); setError(`Case ${requested} was not found.`); }
      else { const latest = Math.max(...options.items.map(row => Number(row.term_year)).filter(Number.isFinite)); const first = options.items.find(row => Number(row.term_year) === latest); setYear(String(latest)); setId(first?.case_number || ''); }
    };
    window.addEventListener('popstate', restore);
    return () => window.removeEventListener('popstate', restore);
  }, [options]);
  useEffect(() => {
    if (!id) return;
    const controller = new AbortController(); setDetail(null); setError('');
    fetch(`/api/cases/${encodeURIComponent(id)}`, {signal:controller.signal}).then(r => {if (!r.ok) throw Error('Could not load this case'); return r.json();}).then(setDetail).catch(e => {if(e.name !== 'AbortError') setError(e.message);});
    return () => controller.abort();
  }, [id]);
  const years = useMemo(() => [...new Set((options?.items || []).map(row => Number(row.term_year)))].sort((a,b) => b-a), [options]);
  const cases = (options?.items || []).filter(row => String(row.term_year) === year);
  const choose = value => {setId(value); if (new URLSearchParams(location.search).get('case') !== String(value)) history.pushState(null, '', link(value));};
  const changeYear = value => {setYear(value); const first = options.items.find(row => String(row.term_year) === value); if(first) choose(first.case_number);};
  const row = detail?.opinion;
  return <div className="layout"><Sidebar><hr/><h2>Case Explorer</h2>
    {options && <><label>Term Year<select value={year} onChange={e => changeYear(e.target.value)}>{years.map(y => <option key={y} value={y}>{y}</option>)}</select></label><label>Select Case<select value={id} onChange={e => choose(e.target.value)}>{!id && <option value="">Select a case</option>}{cases.map((item,i) => <option key={`${item.case_number}-${i}`} value={item.case_number}>{item.case_name} ({item.case_number})</option>)}</select></label><hr/><p className="caption">Last updated: {options.updated}</p><p className="caption">{options.items.length} opinions in dataset</p></>}
  </Sidebar><main><div className="brand"><img src="/logo.png" alt="Granite State Appeals"/><div><h1>Granite State Appeals</h1><p className="caption">NH Supreme Court Analytics</p></div></div><hr/>
    {error && <p role="alert" className="error">{error}</p>}{row && <><div className="case-columns"><div><h2>{row.case_name}</h2><p><b>Citation:</b> {detail.citation || '—'} {row.pdf_url && <a href={row.pdf_url} target="_blank" rel="noreferrer">View PDF ↗</a>}</p><p>{[row.date_argued && `Argued: ${String(row.date_argued).slice(0,10)}`,row.date_issued && `Decided: ${String(row.date_issued).slice(0,10)}`,row.days_to_decision && `(${row.days_to_decision} days)`].filter(Boolean).join(' · ')}</p>
      {row.lower_court && <p><b>Lower Court:</b> {row.lower_court}</p>}{row.lower_court_judge && <p><b>Trial Court Judge:</b> {row.lower_court_judge}</p>}{row.appeal_type && <p><b>Appeal Type:</b> {title(row.appeal_type)}</p>}{row.outcome && <span className="outcome" style={{background: detail.outcome_color}}>{detail.outcome_label}</span>}
      <p>{detail.topics.map(t => <span className="chip" key={t}>{title(t)}</span>)}</p>
      {detail.counsel.length > 0 && <><b>Brief counsel</b><ul>{detail.counsel.filter((fact,i,items) => fact.attorney_raw && items.findIndex(x => x.side === fact.side && x.attorney_raw === fact.attorney_raw) === i).map((fact,i) => <li key={i}><b>{title(fact.side || 'other')}:</b> <a href={`/attorney-profile?attorney=${encodeURIComponent(fact.attorney_raw)}`}>{fact.attorney_raw}</a></li>)}</ul></>}
      {!detail.counsel.length && detail.appearance_rows?.length > 0 && <><b>Counsel</b><ul>{detail.appearance_rows.flatMap(row => row.participants.map((name,i) => <li key={`${row.side}-${name}-${i}`}><b>{row.side}:</b> <a href={`/attorney-profile?attorney=${encodeURIComponent(name)}`}>{name}</a></li>))}</ul></>}
      {!detail.counsel.length && !detail.appearance_rows?.length && detail.appearance && <><b>Counsel</b><p className="opinion-text">{detail.appearance}</p></>}
      {detail.bench_chart && <><b>Bench Vote</b><div className="bench-plot"><Plot figure={detail.bench_chart}/></div><div>{Object.entries(detail.vote_colors).map(([name,color]) => <span className="vote-legend" key={name} style={{background:color}}>{title(name)}</span>)}</div></>}
    </div><div>{row.author_display && <><b>Opinion Author</b><div className="case-metric">{row.author_display}</div></>}{row.vote_string && <><b>Vote</b><div className="case-metric">{row.vote_string}</div></>}{row.is_unanimous ? <div className="notice success">Unanimous decision</div> : row.has_dissent ? <div className="notice divided">Divided decision (dissent)</div> : null}{detail.statutes.length > 0 && <><b>Statutes at Issue</b><ul>{detail.statutes.slice(0,8).map(s => <li key={s}>{s}</li>)}</ul></>}</div></div>
    {detail.argument && <section><hr/><div className="research"><b>Oral Argument Transcript</b><p className="caption">Machine-generated beta transcript. Speaker labels are inferred and may be inaccurate.</p><p><a href={`/oral-arguments?argument=${encodeURIComponent(detail.argument.case_number)}`}>Read the oral argument transcript</a></p>{detail.argument.vimeo_url && <p><a href={detail.argument.vimeo_url} target="_blank" rel="noreferrer">Watch the original argument on Vimeo</a></p>}{detail.roster.length > 0 && <><b>Oral-argument roster</b><ul>{detail.roster.map((a,i) => <li key={i}>{title(a.side || 'other')}: {a.name}{a.firm ? ` (${a.firm})` : ''}</li>)}</ul></>}</div></section>}
    {(detail.cites.length > 0 || detail.cited_by.length > 0) && <section><hr/>{[['📑 Cases Cited',detail.cites,detail.cites_count],['🔗 Cited By',detail.cited_by,detail.cited_by_count]].map(([label,items,count]) => items.length > 0 && <details key={label}><summary>{label} ({count})</summary><ul>{items.map((caseItem,i) => <li key={i}>{caseItem.case_name === caseItem.case_number ? caseItem.case_number : <a href={link(caseItem.case_number)}>{caseItem.case_name}</a>}{caseItem.citation && caseItem.case_name !== caseItem.case_number ? ` · ${caseItem.citation}` : ''}</li>)}</ul></details>)}</section>}
    {(detail.intro || row.summary_paragraph) && <section><hr/><b>Summary</b><p className="opinion-text">{detail.intro || row.summary_paragraph}</p></section>}<details><summary>Read Full Opinion Text</summary>{detail.text ? <p className="opinion-text">{detail.text.split(/(RSA\s+[\d\-A-Z:]+)/g).map((part,i) => /^RSA\s/.test(part) ? <mark key={i}>{part}</mark> : part)}</p> : <p>Full text not available for this opinion.</p>}</details></>}
    <footer><b>Part of <a href="http://www.gavel-glimpse.com">Gavel Glimpse</a></b><p>This public legal-data site is created for informational and research purposes only. It does not provide legal advice and is not a substitute for consulting a qualified attorney.</p></footer>
  </main></div>;
}
