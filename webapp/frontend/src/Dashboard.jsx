import React, { useEffect, useRef, useState } from 'react';
import {recordPrivacySafeEvent} from './privacyTelemetry.js';

function safeCaseHref(raw) {
  try {
    const url = new URL(raw, window.location.origin);
    const caseId = url.searchParams.get('case');
    if (url.origin !== window.location.origin || url.pathname !== '/case-explorer' || !/^[A-Za-z0-9_-]+$/.test(caseId || '')) return null;
    return `/case-explorer?case=${encodeURIComponent(caseId)}`;
  } catch { return null; }
}

function safeMarkdownHref(raw) {
  const internal = safeCaseHref(raw);
  if (internal) return internal;
  try {
    const url = new URL(raw, window.location.origin);
    return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : null;
  } catch { return null; }
}

function inlineMarkdown(text, prefix = 'answer') {
  const pattern = /\[([^\]]+)\]\(([^)]+)\)|\*\*([^*]+)\*\*|~~([^~]+)~~|`([^`]+)`|\*([^*]+)\*/g;
  const nodes = [];
  let last = 0, match, index = 0;
  while ((match = pattern.exec(text))) {
    if (match.index > last) nodes.push(text.slice(last, match.index));
    if (match[1] !== undefined) {
      const href = safeMarkdownHref(match[2]);
      const external = href && new URL(href, window.location.origin).origin !== window.location.origin;
      nodes.push(href ? <a key={`${prefix}-${index}`} href={href} target={external ? '_blank' : undefined} rel={external ? 'noreferrer' : undefined}>{inlineMarkdown(match[1], `${prefix}-${index}`)}</a> : match[1]);
    } else if (match[3] !== undefined) nodes.push(<strong key={`${prefix}-${index}`}>{match[3]}</strong>);
    else if (match[4] !== undefined) nodes.push(<del key={`${prefix}-${index}`}>{match[4]}</del>);
    else if (match[5] !== undefined) nodes.push(<code key={`${prefix}-${index}`}>{match[5]}</code>);
    else nodes.push(<em key={`${prefix}-${index}`}>{match[6]}</em>);
    last = pattern.lastIndex;
    index++;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

function AnswerMarkdown({text}) {
  const blocks = String(text || '').trim().split(/\n\s*\n/).filter(Boolean);
  return <div className="answer-text">{blocks.map((block, i) => {
    const lines = block.split('\n');
    if (block.startsWith('```') && block.endsWith('```')) return <pre key={i}><code>{block.slice(block.indexOf('\n') + 1, -3)}</code></pre>;
    if (lines.length > 1 && /^\s*\|?.+\|.+\|?\s*$/.test(lines[0]) && /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(lines[1])) {
      const cells = line => line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(cell => cell.trim());
      return <div className="table-wrap" key={i}><table><thead><tr>{cells(lines[0]).map((cell,j)=><th key={j}>{inlineMarkdown(cell,`table-head-${i}-${j}`)}</th>)}</tr></thead><tbody>{lines.slice(2).filter(line=>line.includes('|')).map((line,j)=><tr key={j}>{cells(line).map((cell,k)=><td key={k}>{inlineMarkdown(cell,`table-cell-${i}-${j}-${k}`)}</td>)}</tr>)}</tbody></table></div>;
    }
    if (lines.every(line => /^\s*[-*+]\s+/.test(line))) return <ul key={i}>{lines.map((line, j) => <li key={j}>{inlineMarkdown(line.replace(/^\s*[-*+]\s+/, ''), `list-${i}-${j}`)}</li>)}</ul>;
    if (lines.every(line => /^\s*\d+[.)]\s+/.test(line))) return <ol key={i}>{lines.map((line, j) => <li key={j}>{inlineMarkdown(line.replace(/^\s*\d+[.)]\s+/, ''), `olist-${i}-${j}`)}</li>)}</ol>;
    if (lines.every(line => /^\s*>\s?/.test(line))) return <blockquote key={i}>{lines.map((line, j) => <React.Fragment key={j}>{j > 0 && <br/>}{inlineMarkdown(line.replace(/^\s*>\s?/, ''), `quote-${i}-${j}`)}</React.Fragment>)}</blockquote>;
    if (/^\s*(---+|\*\*\*+|___+)\s*$/.test(block)) return <hr key={i}/>;
    const heading = block.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      const Tag = `h${Math.min(6, heading[1].length + 1)}`;
      return <Tag key={i}>{inlineMarkdown(heading[2], `heading-${i}`)}</Tag>;
    }
    return <p key={i}>{lines.map((line, j) => <React.Fragment key={j}>{j > 0 && <br/>}{inlineMarkdown(line, `paragraph-${i}-${j}`)}</React.Fragment>)}</p>;
  })}</div>;
}

export default function Dashboard() {
  const [data, setData] = useState(null), [error, setError] = useState('');
  const [query, setQuery] = useState(''), [limit, setLimit] = useState(8), [results, setResults] = useState(null);
  const [selected, setSelected] = useState(null), [busy, setBusy] = useState(false);
  const [answer, setAnswer] = useState(null);
  const [previousQuery, setPreviousQuery] = useState(''), [previousCases, setPreviousCases] = useState([]), [previousAnswer, setPreviousAnswer] = useState('');
  const [searchStatus, setSearchStatus] = useState('');
  const selectionRequest = useRef(0);
  useEffect(() => { fetch('/api/dashboard').then(r => { if (!r.ok) throw Error('Could not load dashboard data'); return r.json(); }).then(setData).catch(e => setError(e.message)); }, []);
  useEffect(() => {
    let active = true, timer;
    async function check() {
      try {
        const response = await fetch('/api/research/status');
        if (!response.ok) return;
        const status = (await response.json()).status;
        if (!active) return;
        setSearchStatus(status);
        if (status === 'warming') timer = setTimeout(check, 3000);
      } catch { /* Search still works if status is temporarily unavailable. */ }
    }
    check();
    return () => { active = false; clearTimeout(timer); };
  }, []);
  async function runResearch(text, mode) {
    if (text.trim().length < 3) return;
    selectionRequest.current++; setBusy(true); setError(''); setSelected(null); setAnswer(null);
    try {
      const response = await fetch(`/api/research/${mode}`, {method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({query:text, limit:Number(limit), previous_query:previousQuery, previous_cases:previousCases, previous_answer:previousAnswer})});
      const body = await response.json(); if (!response.ok) throw Error(body.detail || 'Search could not be completed');
      setResults(body.results); if (!body.results?.length) recordPrivacySafeEvent('zero_result_search', {surface: 'case_explorer'}); if (mode === 'answer') { if (body.verified_claims?.length) recordPrivacySafeEvent('verified_research_task', {surface: 'case_explorer_ai', verified_claim_count: body.verified_claims.length}); else recordPrivacySafeEvent('answer_abstention', {surface: 'case_explorer_ai'}); } setPreviousQuery(text); setPreviousCases(body.results || []); if (mode === 'answer' && body.answer) { setAnswer(body); setPreviousAnswer(body.answer); }
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  function search(event) {
    event.preventDefault();
    runResearch(query, event.nativeEvent.submitter?.value === 'answer' ? 'answer' : 'search');
  }
  async function show(item, index) {
    const request = ++selectionRequest.current;
    const id = item.docket_number || item.case_number || item.href || '';
    setError(''); setSelected({item, index, opinion:null});
    if (!id) return;
    try {
      const response = await fetch(`/api/opinions/${encodeURIComponent(id)}`);
      if (response.status === 404) return;
      if (!response.ok) throw Error('Could not load case details');
      const detail = await response.json();
      if (request === selectionRequest.current) setSelected({item, index, opinion:detail.opinion});
    } catch(e) { if (request === selectionRequest.current) setError(e.message); }
  }
  function followUp(text) { setQuery(text); runResearch(text, 'answer'); }
  const named = (answer?.results || []).filter(item => item.name && item.name !== 'Error');
  const followUps = named.length ? [`What were the key facts in ${named[0].name}?`, ...(named[1] ? [`Compare the reasoning in ${named[0].name} and ${named[1].name}.`, `How do the holdings in ${named[0].name} and ${named[1].name} differ?`] : [`What rule did ${named[0].name} establish?`, `What did the dissent say in ${named[0].name}?`])] : [];
  const history = data?.history || [], first = history[0];
  return <main className="dashboard"><div className="brand dashboard-brand"><img src="/logo.png" alt="Granite State Appeals"/><div><h1>Granite State Appeals</h1><p className="caption">NH Supreme Court analytics, opinions, case orders, and court trends</p></div></div>
    {error && <p className="error" role="alert">{error}</p>}
    {first && <><div className="history-card"><img src="/onthisday.png" alt="On this day"/><div><span className="caption">{data.history_exact ? 'On this date' : 'Nearest court date'}</span><h3>On This Day in NH Supreme Court History</h3><p><strong>{new Date(`${first.date_issued.slice(0,10)}T12:00:00`).toLocaleDateString('en-US', {month:'long',day:'numeric'})}</strong> · <a href={`/case-explorer?case=${encodeURIComponent(first.case_number)}`}>{first.case_name}</a> was decided ({first.term_year}){first.citation || first.case_number ? ` · ${first.citation || first.case_number}` : ''}</p><p>Decided {new Date(`${first.date_issued.slice(0,10)}T12:00:00`).toLocaleDateString('en-US', {month:'short',day:'numeric',year:'numeric'})} · {history.length > 1 ? `${history.length - 1} more opinion${history.length === 2 ? '' : 's'} from this date` : 'One opinion from this date'}</p></div></div>
    {history.length > 1 && <details className="history-expander"><summary>View all {history.length} opinions from {new Date(`${first.date_issued.slice(0,10)}T12:00:00`).toLocaleDateString('en-US', {month:'long',day:'numeric'})}</summary><ul>{history.map((row,i) => <li key={`${row.case_number}-${i}`}><a href={`/case-explorer?case=${encodeURIComponent(row.case_number)}`}>{row.case_name}</a> ({row.term_year}) {row.citation && `· ${row.citation}`}</li>)}</ul></details>}</>}
    <h2>Top Issues</h2>{data?.topics?.length ? <div>{data.topics.map(topic => <a className="chip" href={`/topics?topic=${encodeURIComponent(topic.name)}`} key={topic.name}>{topic.name.replaceAll('_',' ').replace(/\b\w/g,c => c.toUpperCase())} · {topic.count}</a>)}</div> : data ? <p className="caption">Topic tags are not available yet.</p> : null}<hr/>
    <form className="research" onSubmit={search}><h3>💬 Ask &amp; Browse</h3><p className="caption">Describe a legal situation or ask a question — AI-powered search across NH Supreme Court opinions.</p><label className="sr-only" htmlFor="research-query">Ask a question or describe a legal situation</label><textarea id="research-query" placeholder={"e.g. police searched a suspect's cell phone without a warrant\ne.g. What are the landmark cases on free speech in schools?\ne.g. Compare specific NH Supreme Court decisions"} value={query} onChange={e => setQuery(e.target.value)}/><div className="research-controls"><label>Results <input type="range" min="3" max="20" value={limit} onChange={e => setLimit(e.target.value)}/> {limit}</label><button value="search" disabled={busy || query.trim().length < 3}>{busy ? 'Searching…' : '🔍 Search'}</button><button className="primary" value="answer" disabled={busy || query.trim().length < 3}>🚀 Ask AI</button></div>
    {searchStatus === 'warming' && <p className="caption" role="status">Search is preparing the opinion index. The first search may take longer.</p>}
    {searchStatus === 'unavailable' && <p className="caption" role="status">Search preparation did not finish; a search will retry it.</p>}
    {answer && <section><hr/><h3>💬 AI Answer</h3><AnswerMarkdown text={answer.answer}/><p className="caption">Claim-level verification · {Math.round(answer.coverage * 100)}% answer coverage · {answer.unsupported_removed} unsupported claim(s) removed{answer.as_of ? ` · authority as of ${answer.as_of}` : ''}</p>{answer.verified_claims.length > 0 && <details><summary>Verified claim evidence ({answer.verified_claims.length})</summary>{answer.verified_claims.map((claim,i) => <div key={i}><b>{claim.claim}</b><p className="caption">{claim.case_id} · entailment {Math.round(claim.entailment_score*100)}% · characters {claim.start_char}–{claim.end_char}</p><p>{claim.source_span}</p></div>)}</details>}{followUps.length > 0 && <section><h4>Suggested follow-up questions</h4>{followUps.map(question => <button className="follow-up" type="button" key={question} disabled={busy} onClick={()=>followUp(question)}>{question}</button>)}</section>}<details><summary>📚 Sources ({answer.results.length} cases)</summary><ul>{answer.results.map((item,i) => {const caseId=item.docket_number || item.case_number; return <li key={i}>{caseId ? <a href={`/case-explorer?case=${encodeURIComponent(caseId)}`}>{item.name}</a> : item.name} · {item.docket_number || item.citation}</li>;})}</ul></details><hr/></section>}
    {results && (results.length ? <div className="result-grid"><div><b>{results.length} result(s) — click a case to read it</b>{results.map((item,i) => <div className="result-card" key={`${item.href || item.name}-${i}`}><b>{i+1}. {item.name}</b><p className="caption">{item.term || item.year} term · score {Number(item.score || 0).toFixed(3)}</p><button type="button" className={selected?.index === i ? 'primary' : undefined} onClick={() => show(item,i)}>{selected?.index === i ? '✅ Selected' : 'View →'}</button> {(item.docket_number || item.case_number) && <a className="download inline-link" href={`/case-explorer?case=${encodeURIComponent(item.docket_number || item.case_number)}`}>Open Case →</a>}</div>)}</div><div>{selected ? <SearchResultDetail selected={selected}/> : <div className="select-case">← Select a case to read it</div>}</div></div> : <p>No matching cases found. Try rephrasing your question.</p>)}
    </form><hr/><h2>Court Snapshot</h2>{data && <><div className="snapshot">{[['Opinions',data.total.toLocaleString()],['Current Term',data.current_year],['Term Opinions',data.term_opinions.toLocaleString()],['Unanimous Rate',`${data.unanimous_rate}%`]].map(([label,value]) => <div key={label}><span className="caption">{label}</span><strong>{value}</strong></div>)}</div><p className="caption">Last updated: {data.updated} · {data.dissent_count.toLocaleString()} opinions include a dissent</p></>}
    <footer><b>Part of <a href="http://www.gavel-glimpse.com">Gavel Glimpse</a></b><p>This public legal-data site is created for informational and research purposes only. It does not provide legal advice and is not a substitute for consulting a qualified attorney.</p></footer>
  </main>;
}

function SearchResultDetail({selected}) {
  const {item,opinion} = selected;
  return <section><h2>{item.name || opinion?.case_name || 'Unknown Case'}</h2><div className="detail"><div>{opinion ? <><p><b>Citation:</b> {opinion.citation || '—'}</p><p><b>Case Number:</b> {opinion.case_number || '—'}</p>{opinion.pdf_url && <p><a href={opinion.pdf_url} target="_blank" rel="noreferrer">View Full Opinion PDF ↗</a></p>}{opinion.date_argued && <p><b>Argued:</b> {String(opinion.date_argued).slice(0,10)}</p>}{opinion.date_issued && <p><b>Decided:</b> {String(opinion.date_issued).slice(0,10)}</p>}</> : <><p><b>Docket:</b> {item.docket_number || item.case_number || '—'}</p>{item.year && <p><b>Year:</b> {item.year}</p>}</>}{item.outcome && item.outcome !== 'Not available' && <span className="outcome search-outcome">{item.outcome}</span>}{item.snippet && <p>{item.snippet}</p>}</div><div><p><b>Author:</b> {opinion?.author_display || item.author || '—'}</p>{opinion && <p><b>Vote:</b> {opinion.vote_string || '—'}</p>}</div></div><hr/>{item.facts_of_the_case && <details open><summary>📋 Facts</summary><p>{item.facts_of_the_case}</p></details>}{item.conclusion && <details><summary>⚖️ Holding</summary><p>{item.conclusion}</p></details>}</section>;
}
