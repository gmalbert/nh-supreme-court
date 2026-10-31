import React from 'react';

export default function NumberStepper({label,value,onChange,min,max,step=1}) {
  const numeric = Number(value);
  const setClamped = next => {
    const bounded = Math.max(min, Math.min(max, next));
    onChange(Number.isInteger(step) ? bounded : Number(bounded.toFixed(6)));
  };
  return <label className="number-stepper-label">{label}<span className="number-stepper">
    <input type="number" value={value} min={min} max={max} step={step}
      onChange={event=>onChange(event.target.value)}
      onBlur={event=>setClamped(Number(event.target.value))} />
    <span className="number-stepper-actions">
      <button type="button" aria-label={`Decrease ${label}`} disabled={numeric<=min}
        onClick={()=>setClamped((Number.isFinite(numeric)?numeric:min)-step)}>−</button>
      <button type="button" aria-label={`Increase ${label}`} disabled={numeric>=max}
        onClick={()=>setClamped((Number.isFinite(numeric)?numeric:min)+step)}>+</button>
    </span>
  </span></label>;
}
