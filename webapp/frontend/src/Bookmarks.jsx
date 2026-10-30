import React,{useEffect,useState} from 'react';
const key='nhsc-bookmarks';
function bookmarks(){try{return JSON.parse(sessionStorage.getItem(key)||'[]');}catch{return [];}}
export function BookmarkButton({opinion}){
 const [saved,setSaved]=useState(()=>bookmarks().some(b=>b.case_number===opinion.case_number));
 useEffect(()=>{const sync=()=>setSaved(bookmarks().some(b=>b.case_number===opinion.case_number));sync();window.addEventListener('nhsc-bookmarks',sync);return()=>window.removeEventListener('nhsc-bookmarks',sync);},[opinion.case_number]);
 function toggle(){const current=bookmarks().filter(b=>b.case_number!==opinion.case_number);if(!saved)current.push({case_number:opinion.case_number,case_name:opinion.case_name,citation:opinion.citation});sessionStorage.setItem(key,JSON.stringify(current));window.dispatchEvent(new Event('nhsc-bookmarks'));}
 return <button type="button" onClick={toggle}>{saved?'🔖 Bookmarked':'📑 Bookmark'}</button>;
}
export function BookmarkList(){const [list,setList]=useState(bookmarks);useEffect(()=>{const update=()=>setList(bookmarks());window.addEventListener('nhsc-bookmarks',update);return()=>window.removeEventListener('nhsc-bookmarks',update);},[]);function remove(id){sessionStorage.setItem(key,JSON.stringify(bookmarks().filter(b=>b.case_number!==id)));window.dispatchEvent(new Event('nhsc-bookmarks'));}if(!list.length)return null;return <><hr/><h3>🔖 Bookmarked Cases</h3>{list.slice(0,5).map(b=><div className="bookmark-row" key={b.case_number}><a href={`/case-explorer?case=${encodeURIComponent(b.case_number)}`}>{b.case_name?.length>30?b.case_name.slice(0,27)+'…':b.case_name}</a><button type="button" aria-label={`Remove ${b.case_name}`} onClick={()=>remove(b.case_number)}>×</button></div>)}{list.length>5 && <small>+{list.length-5} more</small>}<button type="button" onClick={()=>{sessionStorage.removeItem(key);window.dispatchEvent(new Event('nhsc-bookmarks'));}}>Clear all</button></>;}
