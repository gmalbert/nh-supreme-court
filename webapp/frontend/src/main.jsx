import CompareCases from './CompareCases.jsx';
import FirmReview from './FirmReview.jsx';
import MultiSelect from './MultiSelect.jsx';
import Sidebar from './Sidebar.jsx';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import Dashboard from './Dashboard.jsx';
import About from './About.jsx';
import CaseExplorer from './CaseExplorer.jsx';
import OralArguments from './OralArguments.jsx';
import Topics from './Topics.jsx';
import Orders from './Orders.jsx';
import TrialCourts from './TrialCourts.jsx';
import Justices from './Justices.jsx';
import Analysis from './Analysis.jsx';
import LegalIntelligence from './LegalIntelligence.jsx';
import {PersonProfile} from './People.jsx';
import './style.css';

function App() {
  const [filters, setFilters] = useState(null);
  const [years, setYears] = useState(() => [0, 1, 2].map(n => String(new Date().getFullYear() - n)));
  const [outcomes, setOutcomes] = useState([]), [authors, setAuthors] = useState([]);
  const [decision, setDecision] = useState('all'), [query, setQuery] = useState('');
  const [page, setPage] = useState(0), [sortBy, setSortBy] = useState('date_issued'), [sortDirection, setSortDirection] = useState('desc');
  const [result, setResult] = useState(null), [selected, setSelected] = useState(null), [error, setError] = useState('');
  const [tableQuery, setTableQuery] = useState(''), [tableSearchOpen, setTableSearchOpen] = useState(false);
  const [columnsOpen, setColumnsOpen] = useState(false), [fullscreenTable, setFullscreenTable] = useState(false);
  const [visibleColumns, setVisibleColumns] = useState(['citation','case_name','date_issued','author_display','vote_string','outcome','pdf_url']);
  const selectionVersion = useRef(0);
  const params = useMemo(() => {
    const p = new URLSearchParams();
    years.forEach(v => p.append('year', v)); outcomes.forEach(v => p.append('outcome', v)); authors.forEach(v => p.append('author', v));
    p.set('decision', decision); p.set('q', query); return p;
  }, [years, outcomes, authors, decision, query]);
  const tableParams = useMemo(() => { const p = new URLSearchParams(params); if (tableQuery) p.set('table_q', tableQuery); return p; }, [params, tableQuery]);
  useEffect(() => { fetch('/api/opinions/filters').then(r => { if (!r.ok) throw Error('Could not load filters'); return r.json(); }).then(setFilters).catch(e => setError(e.message)); }, []);
  useEffect(() => { selectionVersion.current++; setPage(0); setSelected(null); }, [params, tableQuery]);
  useEffect(() => {
    const controller = new AbortController(); const p = new URLSearchParams(tableParams); p.set('offset', String(page * 500)); p.set('limit', '500'); p.set('sort_by', sortBy); p.set('sort_direction', sortDirection);
    fetch(`/api/opinions?${p}`, {signal: controller.signal}).then(r => { if (!r.ok) throw Error('Could not load opinions'); return r.json(); }).then(data => { setResult(data); setError(''); }).catch(e => { if (e.name !== 'AbortError') setError(e.message); });
    return () => controller.abort();
  }, [tableParams, page, sortBy, sortDirection]);
  async function select(item) {
    const version = ++selectionVersion.current;
    try { const response = await fetch(`/api/opinions/${encodeURIComponent(item.case_number)}`); if (!response.ok) throw Error('Could not load opinion'); const data = await response.json(); if (version === selectionVersion.current) { setSelected(data); setError(''); } }
    catch (e) { if (version === selectionVersion.current) setError(e.message); }
  }
  const display = v => v == null || String(v).trim() === '' || String(v).trim().toLowerCase() === 'nan' ? '—' : String(v);
  const cleanSummary = value => String(value || '').replaceAll('�','').trim().replace(/^[\s\]\[(){}"'“”‘’`]+|[\s\]\[(){}"'“”‘’`]+$/g,'').trim();
  const selectedOutcome = filters?.outcomes.find(o => o.value === selected?.opinion.outcome);
  const summary = cleanSummary(selected?.opinion.summary_paragraph);
  const columns = [['citation','Citation'],['case_name','Case Name'],['date_issued','Date Issued'],['author_display','Author Display'],['vote_string','Vote String'],['outcome','Outcome'],['pdf_url','PDF']];
  const displayColumns = columns.filter(([key]) => visibleColumns.includes(key));
  useEffect(() => { if (!fullscreenTable) return; const onKey = e => { if (e.key === 'Escape') setFullscreenTable(false); }; document.addEventListener('keydown', onKey); return () => document.removeEventListener('keydown', onKey); }, [fullscreenTable]);
  function sortOpinions(key) { setSortDirection(sortBy === key && sortDirection === 'asc' ? 'desc' : 'asc'); setSortBy(key); setPage(0); }
  if (location.pathname === '/') return <div className="layout"><Sidebar></Sidebar><Dashboard/></div>;
  return <div className="layout"><Sidebar><hr/><h2>Filters</h2>
    {filters && <><MultiSelect label="Year(s)" options={Array.from({length: new Date().getFullYear()-1999}, (_, i) => ({value: String(2000+i), label: String(2000+i)}))} value={years} onChange={setYears}/>
      <MultiSelect label="Outcome" options={filters.outcomes} value={outcomes} onChange={setOutcomes}/><MultiSelect label="Opinion Author" options={filters.authors} value={authors} onChange={setAuthors}/>
      <label>Decision Type<select value={decision} onChange={e => setDecision(e.target.value)}><option value="all">All</option><option value="unanimous">Unanimous</option><option value="dissent">Divided (dissent)</option><option value="concurrence">Separate concurrence</option></select></label>
      <label>Search case name or RSA<input value={query} onChange={e => setQuery(e.target.value)}/></label><img className="sidebar-logo" src="/logo.png" alt="Granite State Appeals"/><small>Last updated: {filters.updated}</small><a className="download" href={`/api/opinions.csv?${params}`}>⬇ Download Filtered CSV</a></>}
  </Sidebar><main className="opinions-page"><h1>Opinions Browser</h1>{error && <p role="alert" className="error">{error}</p>}{result && <><p className="caption">Showing {result.filtered_count ?? result.count} of {result.total} opinions</p><div className="dataframe-toolbar" aria-label="Table tools"><button type="button" aria-expanded={tableSearchOpen} onClick={() => { setTableSearchOpen(v => !v); if (tableSearchOpen) setTableQuery(''); }}>Search</button>{tableSearchOpen && <input className="table-search" aria-label="Search table" placeholder="Search displayed data" value={tableQuery} onChange={e => setTableQuery(e.target.value)}/>}<div className="column-chooser"><button type="button" aria-expanded={columnsOpen} onClick={() => setColumnsOpen(v => !v)}>Show/hide columns</button>{columnsOpen && <div className="column-chooser-menu">{columns.map(([key,label]) => <label key={key}><input type="checkbox" checked={visibleColumns.includes(key)} onChange={e => setVisibleColumns(v => e.target.checked ? [...v,key] : v.filter(c => c !== key))}/>{label}</label>)}</div>}</div><a className="toolbar-download" href={`/api/opinions.csv?${params}`} download>Download as CSV</a><button type="button" aria-pressed={fullscreenTable} onClick={() => setFullscreenTable(v => !v)}>{fullscreenTable ? 'Exit fullscreen' : 'Fullscreen'}</button></div>{tableQuery && <p className="caption table-match-count">{result.count.toLocaleString()} matching rows</p>}<div className={`table-wrap opinion-table-wrap${fullscreenTable?' opinion-table-fullscreen':''}`}><table><thead><tr><th className="select-cell"><span className="sr-only">Select</span></th>{displayColumns.map(([key,label]) => <th key={key} aria-sort={key==='pdf_url'?'none':sortBy===key?(sortDirection==='asc'?'ascending':'descending'):'none'}>{key==='pdf_url'?label:<button type="button" className="table-sort" onClick={() => sortOpinions(key)}>{label}{sortBy===key?(sortDirection==='asc'?' ▲':' ▼'):''}</button>}</th>)}</tr></thead><tbody>
    {result.items.map((row, i) => <tr key={`${row.case_number}-${i}`} onClick={() => select(row)} onKeyDown={e => { if (e.key === 'Enter') select(row); }} tabIndex="0"><td className="select-cell"><span className={`row-select ${selected?.opinion.case_number === row.case_number ? "selected" : ""}`} aria-hidden="true"/></td>{displayColumns.map(([key]) => <td key={key}>{key==='pdf_url' ? row.pdf_url && <a href={row.pdf_url} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()}>View ↗</a> : key==='outcome' ? display(filters?.outcomes.find(o => o.value === row.outcome)?.label || row.outcome) : display(row[key])}</td>)}</tr>)}
    </tbody></table></div>{result.count > 500 && <div className="pagination"><button disabled={!page} onClick={() => setPage(page-1)}>Previous</button><span>Page {page+1}</span><button disabled={(page+1)*500 >= result.count} onClick={() => setPage(page+1)}>Next</button></div>}</>}
    {selected && <section><hr/><h2>{selected.opinion.case_name}</h2><div className="detail"><div><p><b>Citation:</b> {display(selected.opinion.citation)}</p><p><b>Case Number:</b> {display(selected.opinion.case_number)}</p>{selected.opinion.pdf_url && <p><a href={selected.opinion.pdf_url} target="_blank" rel="noreferrer">View Full Opinion PDF ↗</a></p>}{selected.opinion.date_argued && <p><b>Argued:</b> {selected.opinion.date_argued.slice(0,10)}</p>}{selected.opinion.date_issued && <p><b>Decided:</b> {selected.opinion.date_issued.slice(0,10)}</p>}{selected.opinion.outcome && <span className="outcome" style={{background:selectedOutcome?.color || '#607D8B'}}>{selectedOutcome?.label || selected.opinion.outcome.replaceAll('_',' ')}</span>}{summary && <p>{summary.length>500 ? summary.slice(0,500)+'...' : summary}</p>}</div><div><p><b>Author:</b> {display(selected.opinion.author_display)}</p><p><b>Vote:</b> {display(selected.opinion.vote_string)}</p></div></div>{selected.text && <details><summary>Read Full Opinion</summary><pre>{selected.text.slice(0,5000)}{selected.text.length > 5000 ? '...' : ''}</pre></details>}</section>}
    <footer><b>Part of <a href="http://www.gavel-glimpse.com">Gavel Glimpse</a></b><p>This public legal-data site is created for informational and research purposes only. It does not provide legal advice and is not a substitute for consulting a qualified attorney.</p></footer>
  </main></div>;
}
const path = location.pathname;
const page = path === '/compare-cases' ? <CompareCases/> : path === '/firm-review' ? <FirmReview/> : path === '/about' ? <About/> : path === '/case-explorer' ? <CaseExplorer/> : path === '/oral-arguments' ? <OralArguments/> : path === '/topics' ? <Topics/> : path === '/case-orders' ? <Orders/> : path === '/trial-courts' ? <TrialCourts/> : path === '/justices' ? <Justices/> : path === '/analysis' ? <Analysis/> : path === '/legal-intelligence' ? <LegalIntelligence/> : path === '/attorney-profile' ? <PersonProfile kind="attorney"/> : path === '/firm-profile' ? <PersonProfile kind="firm"/> : path === '/' || path === '/opinions' ? <App/> : <div className="layout"><Sidebar/><main><h1>Page not found</h1><p>The page you requested does not exist.</p><a className="button-link" href="/">Return to Dashboard</a></main></div>;
createRoot(document.getElementById('root')).render(page);
