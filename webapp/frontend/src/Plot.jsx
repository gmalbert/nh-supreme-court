import React, {useEffect, useRef, useState} from 'react';

let plotlyPromise;
const streamlitColors = ['#0068c9','#83c9ff','#ff2b2b','#ffabab','#29b09d','#7defa1','#ff8700','#ffd16a','#6d3fc0','#d5dae5'];
const textColor = '#31333f';
const mutedColor = '#808495';
const gridColor = '#e6e9ef';
const chartFont = 'Source Sans, Arial, sans-serif';

function loadPlotly() {
  if (window.Plotly) return Promise.resolve(window.Plotly);
  if (!plotlyPromise) {
    plotlyPromise = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = '/api/assets/plotly.min.js';
      script.onload = () => resolve(window.Plotly);
      script.onerror = () => {
        plotlyPromise = null;
        reject(Error('Could not load charts'));
      };
      document.head.appendChild(script);
    });
  }
  return plotlyPromise;
}

function titleFont(font = {}) {
  return {family: chartFont, size: 12, color: mutedColor, ...font};
}

function streamlitLayout(figure, horizontal) {
  const source = figure.layout || {};
  const layout = {
    ...source,
    autosize: true,
    colorway: source.colorway || streamlitColors,
    font: {family: chartFont, size: 14, color: textColor, ...source.font},
    paper_bgcolor: source.paper_bgcolor || '#ffffff',
    plot_bgcolor: source.plot_bgcolor || '#ffffff',
    legend: {
      ...source.legend,
      font: {family: chartFont, size: 14, color: mutedColor, ...source.legend?.font},
    },
  };

  if (source.title) {
    const title = typeof source.title === 'string' ? {text: source.title} : {...source.title};
    const titleText = String(title.text || '');
    if (titleText && !/<b\b/i.test(titleText)) title.text = `<b>${titleText}</b>`;
    layout.title = {
      ...title,
      x: title.x ?? 0,
      xanchor: title.xanchor ?? 'left',
      font: {family: chartFont, size: 16, color: textColor, ...title.font},
    };
  }

  for (const key of Object.keys(source)) {
    if (!/^([xy]axis)(\d+)?$/.test(key) || !source[key]) continue;
    const axis = {...source[key]};
    const axisTitle = typeof axis.title === 'string' ? {text: axis.title} : {...axis.title};
    if (axisTitle.text || axisTitle.font) {
      axis.title = {
        ...axisTitle,
        font: titleFont(axisTitle.font),
        standoff: axisTitle.standoff ?? (key.startsWith('yaxis') ? 16 : 12),
      };
    }
    axis.automargin = true;
    axis.tickfont = {family: chartFont, size: 14, color: mutedColor, ...axis.tickfont};
    axis.tickcolor = axis.tickcolor || gridColor;
    axis.zerolinecolor = axis.zerolinecolor || gridColor;
    if (key.startsWith('xaxis')) axis.showgrid ??= false;
    else axis.gridcolor = axis.gridcolor || gridColor;
    layout[key] = axis;
  }

  if (horizontal) {
    layout.margin = {...layout.margin, l: layout.margin?.l ?? 190, r: layout.margin?.r ?? 0};
    const axis = {...(layout.yaxis || {})};
    axis.automargin = false;
    axis.title = typeof axis.title === 'string' ? {text: axis.title} : {...axis.title};
    axis.title = {...axis.title, font: titleFont(axis.title.font), standoff: axis.title.standoff ?? 15};
    layout.yaxis = axis;
  }

  return layout;
}

export default function Plot({figure, height, className = ''}) {
  const element = useRef(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!figure) return undefined;
    let active = true;
    const target = element.current;
    const horizontal = figure.data?.some(trace => trace.orientation === 'h');
    const layout = streamlitLayout(figure, horizontal);
    if (height) layout.height = height;

    loadPlotly()
      .then(plotly => {
        if (active && target) plotly.react(target, figure.data, layout, {responsive: true, displaylogo: false});
      })
      .catch(reason => {
        if (active) setError(reason.message);
      });

    return () => {
      active = false;
      if (window.Plotly && target) window.Plotly.purge(target);
    };
  }, [figure, height]);

  return figure ? <div className={className}>{error && <p role="alert">{error}</p>}<div ref={element} className="plot"/></div> : null;
}
