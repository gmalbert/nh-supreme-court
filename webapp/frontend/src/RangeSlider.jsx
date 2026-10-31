import React from 'react';

export default function RangeSlider({label, min, max, low, high, onLow, onHigh, className = ''}) {
  const floor = Number(min), ceiling = Math.max(Number(max), Number(min) + 1);
  const lower = Math.min(Math.max(Number(low), floor), Number(high));
  const upper = Math.max(Math.min(Number(high), ceiling), lower);
  const span = ceiling - floor;
  const lowerPct = ((lower - floor) / span) * 100;
  const upperPct = ((upper - floor) / span) * 100;
  const fill = `linear-gradient(to right,#d4d6dc 0%,#d4d6dc ${lowerPct}%,#ff4b4b ${lowerPct}%,#ff4b4b ${upperPct}%,#d4d6dc ${upperPct}%,#d4d6dc 100%)`;

  return <fieldset className={`range-filter ${className}`.trim()}>
    <legend>{label}</legend>
    <div className="range-values"><span>{lower}</span><span>{upper}</span></div>
    <div className="double-range" style={{'--range-track': fill}}>
      <input aria-label={`${label} minimum`} type="range" min={floor} max={upper} value={lower} onChange={e => onLow(Number(e.target.value))}/>
      <input aria-label={`${label} maximum`} type="range" min={lower} max={ceiling} value={upper} onChange={e => onHigh(Number(e.target.value))}/>
    </div>
  </fieldset>;
}
