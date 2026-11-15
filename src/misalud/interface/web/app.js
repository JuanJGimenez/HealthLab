/* MiSalud window script.
 *
 * This file only draws. Every number on screen comes from Python through the
 * bridge (`window.pywebview.api`); nothing here reads files or computes metrics.
 * Every visible text comes from the language files through `t(key)`.
 */
(function () {
'use strict';

/* ---------- bridge, texts and formatting ---------- */
const $ = (selector, root) => (root || document).querySelector(selector);
const $$ = (selector, root) => Array.from((root || document).querySelectorAll(selector));
const call = (name, ...args) => window.pywebview.api[name](...args);

const state = {period: 'all', nights: 'all', tab: 'oxygen', x: 'night_hr_avg', y: 'low_minutes',
  sort: ['night_date', -1], texts: {}, language: 'es', theme: 'system', boot: null, data: null};
let T = null;                     // colour tokens read from the stylesheet
const charts = {};

function t(key, values) {
  let text = state.texts[key];
  if (text === undefined) return key;
  Object.entries(values || {}).forEach(([name, value]) => { text = text.split('{' + name + '}').join(value); });
  return text;
}
const locale = () => (state.language === 'en' ? 'en-US' : 'es-AR');
const fmt = (value, digits = 1) => (value === null || value === undefined || Number.isNaN(value)) ? '–'
  : Number(value).toLocaleString(locale(), {minimumFractionDigits: digits, maximumFractionDigits: digits});
const utc = iso => { const [y, m, d] = iso.slice(0, 10).split('-').map(Number); return Date.UTC(y, m - 1, d); };
const fdate = iso => iso ? new Date(utc(iso)).toLocaleDateString(locale(), {day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC'}) : '–';
const fmonth = iso => new Date(utc(iso)).toLocaleDateString(locale(), {month: 'short', year: '2-digit', timeZone: 'UTC'}).replace('.', '');
const fmoment = iso => iso ? new Date(iso).toLocaleString(locale(), {dateStyle: 'medium', timeStyle: 'short'}) : '–';
const fsize = bytes => fmt(bytes / 1048576, 1) + ' MB';
const hhmm = hour => {
  if (hour === null || hour === undefined) return '–';
  const total = Math.round((((hour % 24) + 24) % 24) * 60) % 1440;
  return String(Math.floor(total / 60)).padStart(2, '0') + ':' + String(total % 60).padStart(2, '0');
};
const weekday = number => t('weekday.' + number);
const WEEKDAYS = [1, 2, 3, 4, 5, 6, 7];

function el(tag, attrs, children) {
  const node = document.createElement(tag);
  Object.entries(attrs || {}).forEach(([name, value]) => {
    if (name === 'text') node.textContent = value;
    else if (name === 'onclick') node.addEventListener('click', value);
    else node.setAttribute(name, value);
  });
  (children || []).forEach(child => node.appendChild(child));
  return node;
}
function applyTexts() {
  document.documentElement.lang = state.language;
  $$('[data-t]').forEach(node => { node.textContent = t(node.dataset.t); });
  $$('[data-label]').forEach(node => node.setAttribute('aria-label', t(node.dataset.label)));
}
const css = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
function readTokens() {
  T = {bg: css('--surface-1'), s2: css('--surface-2'), line: css('--line'), grid: css('--grid'), tp: css('--text-primary'),
    ts: css('--text-secondary'), tm: css('--text-muted'), c1: css('--s1'), c2: css('--s2'), c3: css('--s3'),
    ramp: [css('--r1'), css('--r2'), css('--r3'), css('--r4')]};
}

/* ---------- chart helpers ---------- */
function chart(id) {
  if (!charts[id]) {
    const node = document.getElementById(id);
    charts[id] = echarts.init(node);
    if (window.ResizeObserver) new ResizeObserver(() => charts[id] && charts[id].resize()).observe(node);
  }
  return charts[id];
}
function emptyChart(id, count) {
  const c = chart(id);
  if (count) return false;
  c.clear();
  c.setOption({title: {text: t('chart.empty'), left: 'center', top: 'middle', textStyle: {color: T.tm, fontSize: 13, fontWeight: 'normal'}}});
  return true;
}
const axisBase = () => ({axisLine: {lineStyle: {color: T.line}}, axisTick: {show: false}, axisLabel: {color: T.ts, fontSize: 11},
  splitLine: {lineStyle: {color: T.grid, type: 'solid'}}});
const baseOption = () => ({
  animation: false, textStyle: {fontFamily: 'inherit'},
  grid: {left: 6, right: 14, top: 30, bottom: 6, containLabel: true},
  tooltip: {trigger: 'axis', confine: true, backgroundColor: T.bg, borderColor: T.line, borderWidth: 1, padding: [8, 10],
    textStyle: {color: T.tp, fontSize: 12}, extraCssText: 'box-shadow:0 4px 16px rgba(0,0,0,.18);border-radius:8px;',
    axisPointer: {type: 'line', lineStyle: {color: T.tm, width: 1}}},
  legend: {top: 0, right: 0, itemWidth: 14, itemHeight: 3, icon: 'rect', itemStyle: {borderWidth: 0}, textStyle: {color: T.ts, fontSize: 12}, itemGap: 14}
});
const escapeHtml = text => String(text).replace(/[&<>"]/g, ch => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[ch]));
function tip(title, items) {
  return '<div style="font-size:11px;color:' + T.ts + ';margin-bottom:4px">' + escapeHtml(title) + '</div>' +
    items.map(item => '<div style="display:flex;align-items:center;gap:8px;margin:2px 0"><span style="width:10px;height:2px;background:' +
      (item.c || T.tm) + ';display:inline-block;flex:none"></span><b style="font-variant-numeric:tabular-nums">' + escapeHtml(item.v) +
      '</b><span style="color:' + T.ts + '">' + escapeHtml(item.l) + '</span></div>').join('');
}
const timeAxis = () => Object.assign(axisBase(), {type: 'time', splitLine: {show: false},
  axisLabel: {color: T.ts, fontSize: 11, hideOverlap: true, formatter: value => fmonth(new Date(value).toISOString())}});
const valueAxis = extra => Object.assign(axisBase(), {type: 'value'}, extra || {});
const categoryAxis = (labels, extra) => Object.assign(axisBase(), {type: 'category', data: labels, splitLine: {show: false}}, extra || {});
const unitName = unit => ({name: unit, nameTextStyle: {color: T.tm, fontSize: 11, align: 'left'}});
const markLine = (y, text, position) => ({silent: true, symbol: 'none', lineStyle: {color: T.tm, type: 'solid', width: 1},
  label: {formatter: text, color: T.ts, fontSize: 11, position: position || 'insideEndTop'}, data: [{yAxis: y}]});
const zoom = slider => {
  const parts = [{type: 'inside', filterMode: 'none'}];
  if (slider) parts.push({type: 'slider', height: 18, bottom: 6, borderColor: T.line, fillerColor: 'rgba(120,120,120,.18)',
    backgroundColor: T.s2, handleSize: 14, moveHandleSize: 0, textStyle: {color: T.ts, fontSize: 11}, showDetail: false});
  return parts;
};
const lineSeries = (name, values, color) => ({type: 'line', name, data: values, symbol: 'circle', symbolSize: 7,
  lineStyle: {width: 2, color}, itemStyle: {color, borderColor: T.bg, borderWidth: 2}});
const monthValues = (months, key) => months.map(month => (month.enough_nights === false ? null : month[key]));

function nightTip(night) {
  return tip(fdate(night.night_date) + ' · ' + weekday(night.weekday), [
    {c: T.c1, v: fmt(night.low_minutes, 1) + ' min', l: t('tip.below90')},
    {v: fmt(night.spo2_min, 0) + ' %', l: t('metric.spo2_min')},
    {v: fmt(night.spo2_avg, 0) + ' %', l: t('metric.spo2_avg')},
    {v: fmt(night.night_hr_avg, 0) + ' ' + t('unit.bpm'), l: t('metric.night_hr_avg')},
    {v: night.snoring_min === null ? t('tip.not_recorded') : fmt(night.snoring_min, 0) + ' min', l: t('metric.snoring_min')}]);
}

/* ---------- headline cards ---------- */
function renderKpis() {
  const o = state.data.overview;
  const share = o.nights_with_oxygen ? fmt(100 * o.nights_sustained_low / o.nights_with_oxygen, 0) : '–';
  const items = [
    [t('kpi.nights'), o.nights ? String(o.nights) : '–', o.nights ? fdate(o.first_night) + ' – ' + fdate(o.last_night) : t('kpi.no_data')],
    [t('kpi.spo2'), fmt(o.average_spo2, 1) + ' %', t('kpi.spo2.note', {n: o.nights_with_oxygen})],
    [t('kpi.sustained', {min: state.boot.sustained_low_min}), String(o.nights_sustained_low), t('kpi.sustained.note', {pct: share})],
    [t('kpi.asleep'), fmt(o.average_asleep_hours, 1) + ' h', t('kpi.asleep.note', {h: fmt(o.average_hours, 1)})],
    [t('kpi.hrv'), fmt(o.median_hrv_ms, 0) + ' ms', t('kpi.hrv.note')],
    [t('kpi.pulse'), fmt(o.average_night_hr, 0) + ' ' + t('unit.bpm'), t('kpi.pulse.note')]
  ];
  const box = $('#kpis');
  box.textContent = '';
  items.forEach(([label, value, note]) => box.appendChild(el('div', {class: 'kpi'}, [
    el('div', {class: 'l', text: label}), el('div', {class: 'v', text: value}), el('div', {class: 'n', text: note})])));
}

/* ---------- oxygen ---------- */
function renderOxygen() {
  const nights = state.data.nights.filter(night => night.has_valid_oxygen);
  const byTime = new Map(nights.map(night => [utc(night.night_date), night]));
  const pointTip = point => { const night = byTime.get(point.value[0]); return night ? nightTip(night) : ''; };
  const limit = state.boot.sustained_low_min;

  if (!emptyChart('o1', nights.length)) {
    chart('o1').setOption(Object.assign(baseOption(), {
      grid: {left: 6, right: 14, top: 26, bottom: 6, containLabel: true}, legend: {show: false},
      tooltip: Object.assign(baseOption().tooltip, {formatter: points => pointTip(points[0])}),
      xAxis: timeAxis(), yAxis: valueAxis(Object.assign({min: 0}, unitName(t('unit.minutes')))), dataZoom: zoom(false),
      series: [{type: 'bar', data: nights.map(night => [utc(night.night_date), night.low_minutes]), barMaxWidth: 6, barMinWidth: 1.5,
        itemStyle: {color: T.c1, borderRadius: [2, 2, 0, 0]}, markLine: markLine(limit, limit + ' min')}]
    }), true);
  }
  if (!emptyChart('o2', nights.length)) {
    chart('o2').setOption(Object.assign(baseOption(), {
      grid: {left: 6, right: 14, top: 26, bottom: 34, containLabel: true}, legend: {show: false},
      tooltip: Object.assign(baseOption().tooltip, {trigger: 'item', formatter: pointTip}),
      xAxis: timeAxis(), yAxis: valueAxis(Object.assign({min: 65, max: 100}, unitName('%'))), dataZoom: zoom(true),
      series: [{type: 'scatter', data: nights.map(night => [utc(night.night_date), night.spo2_min]), symbolSize: 6,
        itemStyle: {color: T.c1, opacity: .8, borderColor: T.bg, borderWidth: 1}, emphasis: {scale: 1.6},
        markLine: markLine(state.boot.low_spo2_pct, state.boot.low_spo2_pct + ' %')}]
    }), true);
    chart('o1').group = chart('o2').group = 'oxygen';
    echarts.connect('oxygen');
  }
  const weekdays = new Map(state.data.oxygen_weekdays.weekdays.map(row => [row.weekday, row]));
  if (!emptyChart('o3', weekdays.size)) {
    const overall = state.data.oxygen_weekdays.overall_share_pct;
    chart('o3').setOption(Object.assign(baseOption(), {
      legend: {show: false},
      tooltip: Object.assign(baseOption().tooltip, {trigger: 'item', formatter: point => {
        const row = weekdays.get(WEEKDAYS[point.dataIndex]);
        return row ? tip(t('tip.night_of', {day: weekday(row.weekday)}), [
          {c: T.c1, v: fmt(row.share_pct, 0) + ' %', l: t('tip.sustained', {min: limit})},
          {v: t('tip.of', {a: row.sustained, b: row.nights}), l: t('tip.nights')}]) : '';
      }}),
      xAxis: categoryAxis(WEEKDAYS.map(weekday)),
      yAxis: valueAxis({min: 0, axisLabel: {color: T.ts, fontSize: 11, formatter: '{value} %'}}),
      series: [{type: 'bar', data: WEEKDAYS.map(day => (weekdays.has(day) ? weekdays.get(day).share_pct : null)), barWidth: '46%',
        itemStyle: {color: T.c1, borderRadius: [4, 4, 0, 0]},
        label: {show: true, position: 'top', color: T.ts, fontSize: 11, formatter: point => (point.value === null ? '' : fmt(point.value, 0) + ' %')},
        markLine: markLine(overall, t('chart.average') + ' ' + fmt(overall, 0) + ' %', 'insideStartTop')}]
    }), true);
  }
  if (!emptyChart('o4', nights.length)) {
    const piece = (min, max, label, index) => ({min, max, label, color: T.ramp[index]});
    const byDate = new Map(nights.map(night => [night.night_date, night]));
    const monthNames = Array.from({length: 12}, (_, m) => new Date(Date.UTC(2024, m, 1)).toLocaleDateString(locale(), {month: 'short', timeZone: 'UTC'}).replace('.', ''));
    chart('o4').setOption({
      animation: false, textStyle: {fontFamily: 'inherit'},
      tooltip: {confine: true, backgroundColor: T.bg, borderColor: T.line, borderWidth: 1, textStyle: {color: T.tp, fontSize: 12},
        extraCssText: 'border-radius:8px;box-shadow:0 4px 16px rgba(0,0,0,.18);',
        formatter: point => { const night = byDate.get(point.value[0]); return night ? nightTip(night) : ''; }},
      visualMap: {type: 'piecewise', orient: 'horizontal', left: 'center', bottom: 0, itemWidth: 14, itemHeight: 10, itemGap: 14,
        textStyle: {color: T.ts, fontSize: 11}, outOfRange: {color: T.s2},
        pieces: [piece(0, 0.999, t('calendar.under1'), 0), piece(1, 4.999, t('calendar.1to5'), 1),
          piece(5, 9.999, t('calendar.5to10'), 2), piece(10, 1e9, t('calendar.10plus'), 3)]},
      calendar: {top: 26, left: 34, right: 12, bottom: 34, cellSize: ['auto', 14], orient: 'horizontal', firstDay: 1,
        range: [nights[0].night_date, nights[nights.length - 1].night_date],
        itemStyle: {color: T.s2, borderWidth: 2, borderColor: T.bg}, splitLine: {show: false}, yearLabel: {show: false},
        monthLabel: {color: T.ts, fontSize: 11, nameMap: monthNames},
        dayLabel: {color: T.tm, fontSize: 10, firstDay: 1, nameMap: [7, 1, 2, 3, 4, 5, 6].map(day => weekday(day).charAt(0))}},
      series: [{type: 'heatmap', coordinateSystem: 'calendar', data: nights.map(night => [night.night_date, night.low_minutes]),
        itemStyle: {borderWidth: 2, borderColor: T.bg, borderRadius: 2}}]
    }, true);
  }
  loadWorst();
}
async function loadWorst() {
  const answer = await call('worst_nights', state.period, state.nights, $('#worst-by').value);
  if (!answer.ok) return;
  buildTable($('#worst'), [
    [t('column.night'), night => fdate(night.night_date) + ' · ' + weekday(night.weekday), 'l'],
    [t('column.low_minutes'), night => fmt(night.low_minutes, 1)],
    [t('column.spo2_min'), night => fmt(night.spo2_min, 0)],
    [t('column.below85'), night => fmt(night.intervals_below_85, 0)],
    [t('column.pulse'), night => fmt(night.night_hr_avg, 0)],
    [t('column.snoring'), night => fmt(night.snoring_min, 0)],
    [t('column.bedtime'), night => hhmm(night.bedtime_hour)]], answer.nights);
}
function buildTable(table, columns, rows, sorting) {
  table.textContent = '';
  const head = table.createTHead().insertRow();
  columns.forEach(column => {
    const th = el('th', column[2] === 'l' ? {class: 'l'} : {});
    if (sorting && column[3]) {
      const arrow = sorting.key === column[3] ? (sorting.direction > 0 ? ' ▲' : ' ▼') : '';
      th.appendChild(el('button', {type: 'button', text: column[0] + arrow, onclick: () => sorting.sort(column[3])}));
    } else th.textContent = column[0];
    head.appendChild(th);
  });
  const body = table.createTBody();
  rows.forEach(row => {
    const tr = body.insertRow();
    columns.forEach(column => { const td = tr.insertCell(); if (column[2] === 'l') td.className = 'l'; td.textContent = column[1](row); });
  });
}

/* ---------- sleep ---------- */
function renderSleep() {
  const months = state.data.sleep_months;
  const labels = months.map(month => fmonth(month.month));
  const hoursTip = points => tip(points[0].axisValue, points.map(point => ({c: point.color, v: fmt(point.value, 1) + ' h', l: point.seriesName})));
  if (!emptyChart('s1', months.length)) chart('s1').setOption(Object.assign(baseOption(), {
    xAxis: categoryAxis(labels, {boundaryGap: false}), yAxis: valueAxis({scale: true, axisLabel: {color: T.ts, fontSize: 11, formatter: '{value} h'}}),
    tooltip: Object.assign(baseOption().tooltip, {formatter: hoursTip}),
    series: [lineSeries(t('sleep.in_bed'), monthValues(months, 'hours'), T.c1), lineSeries(t('sleep.asleep'), monthValues(months, 'asleep_hours'), T.c2)]
  }), true);
  if (!emptyChart('s2', months.length)) chart('s2').setOption(Object.assign(baseOption(), {
    legend: {show: false}, grid: {left: 6, right: 14, top: 14, bottom: 6, containLabel: true},
    xAxis: categoryAxis(labels, {boundaryGap: false}), yAxis: valueAxis({scale: true}),
    tooltip: Object.assign(baseOption().tooltip, {formatter: points => tip(points[0].axisValue, [{c: T.c1, v: fmt(points[0].value, 0), l: t('sleep.average_score')}])}),
    series: [lineSeries(t('metric.score'), monthValues(months, 'score'), T.c1)]
  }), true);
  const stack = (name, key, color) => ({type: 'bar', name, stack: 'stages', data: monthValues(months, key), barMaxWidth: 34,
    itemStyle: {color, borderColor: T.bg, borderWidth: 2}, emphasis: {focus: 'series'}});
  if (!emptyChart('s3', months.length)) chart('s3').setOption(Object.assign(baseOption(), {
    xAxis: categoryAxis(labels), yAxis: valueAxis({min: 0, axisLabel: {color: T.ts, fontSize: 11, formatter: '{value} min'}}),
    legend: Object.assign(baseOption().legend, {itemWidth: 12, itemHeight: 10}),
    tooltip: Object.assign(baseOption().tooltip, {formatter: points => tip(points[0].axisValue,
      points.slice().reverse().map(point => ({c: point.color, v: fmt(point.value, 0) + ' min', l: point.seriesName})))}),
    series: [stack(t('stage.deep'), 'deep_min', T.c1), stack(t('stage.rem'), 'rem_min', T.c2), stack(t('stage.light'), 'light_min', T.c3)]
  }), true);
}

/* ---------- heart ---------- */
function trendChart(id, key, trend, unit, label) {
  const points = state.data.nights.filter(night => night[key] !== null);
  if (emptyChart(id, points.length)) return;
  const byTime = new Map(points.map(night => [utc(night.night_date), night]));
  chart(id).setOption(Object.assign(baseOption(), {
    tooltip: Object.assign(baseOption().tooltip, {trigger: 'item', formatter: point => {
      if (point.seriesIndex === 1) return tip(fdate(new Date(point.value[0]).toISOString()), [{c: T.c1, v: fmt(point.value[1], 0) + ' ' + unit, l: t('heart.median14')}]);
      const night = byTime.get(point.value[0]);
      return night ? tip(fdate(night.night_date) + ' · ' + weekday(night.weekday), [{c: T.c1, v: fmt(night[key], 0) + ' ' + unit, l: label}]) : '';
    }}),
    xAxis: timeAxis(), yAxis: valueAxis(Object.assign({scale: true}, unitName(unit))), dataZoom: zoom(false),
    series: [
      {type: 'scatter', name: t('heart.each_night'), data: points.map(night => [utc(night.night_date), night[key]]), symbolSize: 5,
        itemStyle: {color: T.c1, opacity: .35}, emphasis: {scale: 1.6, itemStyle: {opacity: 1}}},
      {type: 'line', name: t('heart.rolling'), data: trend.map(point => [utc(point.night_date), point.value]), showSymbol: false,
        lineStyle: {width: 2.5, color: T.c1}, itemStyle: {color: T.c1}, z: 3}]
  }), true);
}
function weekdayChart(id, rows, key, unit, label) {
  const byDay = new Map(rows.map(row => [row.weekday, row]));
  if (emptyChart(id, rows.filter(row => row.nights).length)) return;
  chart(id).setOption(Object.assign(baseOption(), {
    legend: {show: false},
    tooltip: Object.assign(baseOption().tooltip, {trigger: 'item', formatter: point => {
      const row = byDay.get(WEEKDAYS[point.dataIndex]);
      return row ? tip(t('tip.night_of', {day: weekday(row.weekday)}), [{c: T.c1, v: fmt(row[key], 0) + ' ' + unit, l: label}, {v: String(row.nights), l: t('tip.nights')}]) : '';
    }}),
    xAxis: categoryAxis(WEEKDAYS.map(weekday)), yAxis: valueAxis({min: 0}),
    series: [{type: 'bar', data: WEEKDAYS.map(day => (byDay.has(day) ? byDay.get(day)[key] : null)), barWidth: '46%',
      itemStyle: {color: T.c1, borderRadius: [4, 4, 0, 0]},
      label: {show: true, position: 'top', color: T.ts, fontSize: 11, formatter: point => (point.value === null ? '' : fmt(point.value, 0))}}]
  }), true);
}
function renderHeart() {
  trendChart('c1', 'hrv_rmssd_ms', state.data.hrv_trend, 'ms', t('metric.hrv_rmssd_ms'));
  trendChart('c2', 'night_hr_avg', state.data.pulse_trend, t('unit.bpm'), t('metric.night_hr_avg'));
  weekdayChart('c3', state.data.hrv_weekdays, 'median', 'ms', t('chart.median'));
  weekdayChart('c4', state.data.pulse_weekdays, 'average', t('unit.bpm'), t('chart.average'));
}

/* ---------- activity ---------- */
function monthBars(id, key, unit, digits, label) {
  const months = state.data.activity_months.filter(month => month[key] !== null);
  if (emptyChart(id, months.length)) return;
  chart(id).setOption(Object.assign(baseOption(), {
    legend: {show: false}, grid: {left: 6, right: 14, top: 14, bottom: 6, containLabel: true},
    tooltip: Object.assign(baseOption().tooltip, {formatter: points => tip(points[0].axisValue, [
      {c: T.c1, v: fmt(points[0].value, digits) + (unit ? ' ' + unit : ''), l: label},
      {v: String(months[points[0].dataIndex].days), l: t('tip.days')}])}),
    xAxis: categoryAxis(months.map(month => fmonth(month.month))), yAxis: valueAxis({min: 0}),
    series: [{type: 'bar', data: months.map(month => month[key]), barMaxWidth: 28, itemStyle: {color: T.c1, borderRadius: [4, 4, 0, 0]}}]
  }), true);
}
function renderActivity() {
  monthBars('a1', 'steps', '', 0, t('activity.steps.label'));
  monthBars('a2', 'exercise_min', 'min', 0, t('activity.exercise.label'));
  monthBars('a3', 'stress_avg', '', 0, t('activity.stress.label'));
}

/* ---------- relate ---------- */
function fillMetricSelects() {
  [['#rx', state.x], ['#ry', state.y]].forEach(([selector, chosen]) => {
    const select = $(selector);
    select.textContent = '';
    state.boot.night_metrics.forEach(metric => select.appendChild(el('option', {value: metric, text: t('metric.' + metric)})));
    select.value = chosen;
  });
}
async function renderRelate() {
  const answer = await call('relate', state.period, state.nights, state.x, state.y);
  if (!answer.ok) return;
  const xLabel = t('metric.' + state.x), yLabel = t('metric.' + state.y);
  if (!emptyChart('r1', answer.points.length)) chart('r1').setOption(Object.assign(baseOption(), {
    legend: {show: false}, grid: {left: 10, right: 20, top: 34, bottom: 30, containLabel: true},
    tooltip: Object.assign(baseOption().tooltip, {trigger: 'item', formatter: point => tip(fdate(point.data[2]), [
      {c: T.c1, v: fmt(point.data[0], 1), l: xLabel}, {v: fmt(point.data[1], 1), l: yLabel}])}),
    xAxis: valueAxis({scale: true, name: xLabel, nameLocation: 'middle', nameGap: 26, nameTextStyle: {color: T.ts, fontSize: 12}}),
    yAxis: valueAxis({scale: true, name: yLabel, nameTextStyle: {color: T.ts, fontSize: 12, align: 'left'}}),
    series: [{type: 'scatter', data: answer.points.map(point => [point.x, point.y, point.night_date]), symbolSize: 7,
      itemStyle: {color: T.c1, opacity: .55, borderColor: T.bg, borderWidth: 1}}]
  }), true);
  const stat = $('#rstat');
  stat.textContent = '';
  if (answer.spearman === null) stat.textContent = t('relate.none', {n: answer.nights});
  else {
    const size = Math.abs(answer.spearman);
    const strength = size < 0.1 ? 'relate.strength.none' : size < 0.3 ? 'relate.strength.weak' : size < 0.5 ? 'relate.strength.moderate' : 'relate.strength.strong';
    stat.appendChild(document.createTextNode(t('relate.spearman') + ' '));
    stat.appendChild(el('b', {text: fmt(answer.spearman, 2)}));
    stat.appendChild(document.createTextNode(' · ' + t(strength) + ' · ' + t('relate.nights', {n: answer.nights}) +
      (answer.enough_nights ? '' : ' · ' + t('relate.few'))));
  }
}

/* ---------- data table ---------- */
const DATA_COLUMNS = [
  ['night_date', night => fdate(night.night_date), 'l'], ['weekday', night => weekday(night.weekday), 'l'],
  ['hours', night => fmt(night.hours, 1)], ['bedtime_hour', night => hhmm(night.bedtime_hour)], ['score', night => fmt(night.score, 0)],
  ['low_minutes', night => (night.has_valid_oxygen ? fmt(night.low_minutes, 1) : '–')],
  ['spo2_min', night => (night.has_valid_oxygen ? fmt(night.spo2_min, 0) : '–')],
  ['spo2_avg', night => (night.has_valid_oxygen ? fmt(night.spo2_avg, 1) : '–')],
  ['hrv_rmssd_ms', night => fmt(night.hrv_rmssd_ms, 0)], ['night_hr_avg', night => fmt(night.night_hr_avg, 0)],
  ['respiratory_rate_avg', night => fmt(night.respiratory_rate_avg, 1)], ['skin_temp_vs_baseline_c', night => fmt(night.skin_temp_vs_baseline_c, 1)],
  ['snoring_min', night => fmt(night.snoring_min, 0)], ['deep_min', night => fmt(night.deep_min, 0)], ['rem_min', night => fmt(night.rem_min, 0)],
  ['steps', night => fmt(night.steps, 0)], ['exercise_min', night => fmt(night.exercise_min, 0)], ['stress_avg', night => fmt(night.stress_avg, 0)]];
function renderData() {
  const [key, direction] = state.sort;
  const rows = state.data.nights.slice().sort((a, b) => {
    const x = a[key], y = b[key];
    if (x === null) return 1;
    if (y === null) return -1;
    return (x < y ? -1 : x > y ? 1 : 0) * direction;
  });
  $('#dstat').textContent = t('data.count', {n: rows.length});
  const title = column => (column === 'night_date' ? t('column.night') : column === 'weekday' ? t('column.weekday') : t('metric.' + column));
  buildTable($('#dt'), DATA_COLUMNS.map(column => [title(column[0]), column[1], column[2], column[0]]), rows,
    {key, direction, sort: chosen => { state.sort = [chosen, state.sort[0] === chosen ? -state.sort[1] : -1]; renderData(); }});
}

/* ---------- dialogs ---------- */
function openDialog(title, body, buttons) {
  $('#dialog-title').textContent = title;
  const box = $('#dialog-body');
  box.textContent = '';
  body.forEach(node => box.appendChild(node));
  const foot = $('#dialog-foot');
  foot.textContent = '';
  (buttons || []).forEach(button => foot.appendChild(button));
  $('#overlay').hidden = false;
}
function closeDialog() { $('#overlay').hidden = true; }
const fact = (label, value) => el('div', {class: 'fact'}, [el('div', {class: 'l', text: label}), el('div', {class: 'v', text: value})]);
const banner = (text, kind) => el('div', {class: 'banner' + (kind ? ' ' + kind : ''), text});
function simpleTable(headers, rows) {
  const table = el('table');
  buildTable(table, headers.map((header, index) => [header[0], row => row[index], header[1]]), rows);
  return el('div', {class: 'tscroll short'}, [table]);
}
function showError(message) { openDialog(t('error.title'), [banner(message, 'error')]); }

async function startImport() {
  const step = el('p', {class: 'stat', text: t('import.choose')});
  openDialog(t('import.title'), [el('div', {class: 'progress'}, [el('span')]), step]);
  const poll = setInterval(async () => {
    const answer = await call('import_step');
    if (answer.ok && answer.step) step.textContent = t('import.step.' + answer.step);
  }, 500);
  const preview = await call('start_import');
  clearInterval(poll);
  if (!preview.ok) return showError(preview.error);
  if (!preview.chosen) return closeDialog();
  showPreview(preview);
}
function showPreview(preview) {
  const totals = preview.totals;
  const body = [
    el('p', {class: 'stat', text: t('import.file', {name: preview.file_name, date: fmoment(preview.exported_at)})}),
    el('p', {class: 'stat', text: t('import.covers', {a: fdate(preview.first_date), b: fdate(preview.last_date)})}),
    el('div', {class: 'facts'}, [fact(t('import.new'), fmt(totals.new, 0)), fact(t('import.updated'), fmt(totals.updated, 0)),
      fact(t('import.unchanged'), fmt(totals.unchanged, 0)), fact(t('import.kept'), fmt(totals.kept, 0)), fact(t('import.rejected'), fmt(preview.rejected, 0))])];
  if (preview.is_older_export) body.push(banner(t('import.older', {n: fmt(totals.superseded, 0)})));
  if (totals.updated_old) body.push(banner(t('import.old_changes', {n: fmt(totals.updated_old, 0)})));
  preview.failed_domains.forEach(failure => body.push(banner(t('import.failed', {domain: failure.domain, reason: failure.reason}), 'error')));
  const blocked = preview.compatibility.filter(finding => finding.severity === 'error').length;
  const warned = preview.compatibility.length - blocked;
  if (preview.compatibility.length) body.push(banner(t('import.compatibility', {errors: blocked, warnings: warned})));
  body.push(el('h3', {text: t('import.by_table')}));
  body.push(simpleTable([[t('column.table'), 'l'], [t('import.new')], [t('import.updated')], [t('import.unchanged')], [t('import.kept')]],
    preview.tables.map(row => [row.table, fmt(row.new, 0), fmt(row.updated, 0), fmt(row.unchanged, 0), fmt(row.kept, 0)])));
  const nothing = totals.new + totals.updated === 0;
  if (nothing) body.push(banner(t('import.nothing')));
  const confirm = el('button', {class: 'btn primary', type: 'button', text: t('import.confirm'), onclick: () => confirmImport(confirm)});
  const cancel = el('button', {class: 'btn', type: 'button', text: t('action.cancel'), onclick: async () => { await call('cancel_import'); closeDialog(); }});
  openDialog(t('import.preview'), body, [cancel, confirm]);
}
async function confirmImport(button) {
  button.setAttribute('disabled', '');
  button.textContent = t('import.merging');
  const result = await call('confirm_import');
  if (!result.ok) return showError(result.error);
  const body = [el('div', {class: 'facts'}, [fact(t('import.new_nights'), fmt(result.new_nights, 0)), fact(t('import.new_days'), fmt(result.new_days, 0)),
    fact(t('import.new'), fmt(result.new_records, 0)), fact(t('import.updated'), fmt(result.updated_records, 0))])];
  body.push(el('p', {class: 'stat', text: result.backup ? t('import.backup', {name: result.backup}) : t('import.no_backup')}));
  openDialog(t('import.done'), body, [el('button', {class: 'btn primary', type: 'button', text: t('action.close'), onclick: closeDialog})]);
  await start();
}

async function showDatabase() {
  const panel = await call('database_panel');
  if (!panel.ok) return showError(panel.error);
  const body = [el('div', {class: 'facts'}, [
    fact(t('database.last_import'), fmoment(panel.last_import)), fact(t('database.until'), fdate(panel.available.last_day)),
    fact(t('database.nights'), fmt(panel.available.nights, 0)), fact(t('database.size'), fsize(panel.size_bytes))])];
  body.push(el('p', {class: 'path', text: panel.folder}));
  const done = el('span', {class: 'stat', 'aria-live': 'polite'});
  body.push(el('div', {class: 'row'}, [
    el('button', {class: 'btn', type: 'button', text: t('database.open_folder'), onclick: () => call('open_data_folder')}),
    el('button', {class: 'btn', type: 'button', text: t('data.download'), onclick: () => exportCsv(done)}), done]));
  body.push(el('h3', {text: t('database.history')}));
  body.push(simpleTable([[t('database.imported'), 'l'], [t('column.file'), 'l'], [t('import.new')], [t('import.updated')], [t('import.rejected')]],
    panel.history.map(row => [fmoment(row.imported_at), row.file_name, fmt(row.new_count, 0), fmt(row.updated_count, 0), fmt(row.rejected_count, 0)])));
  body.push(el('h3', {text: t('database.issues')}));
  body.push(panel.issues.length
    ? simpleTable([[t('column.table'), 'l'], [t('database.rule'), 'l'], [t('database.action'), 'l'], [t('database.records')]],
      panel.issues.map(row => [row.table, t('rule.' + row.rule), t('issue.' + row.action), fmt(row.records, 0)]))
    : el('p', {class: 'stat', text: t('database.no_issues')}));
  body.push(el('h3', {text: t('database.tables')}));
  body.push(simpleTable([[t('column.table'), 'l'], [t('database.records')], [t('database.from')], [t('database.to')]],
    panel.tables.map(row => [row.table, fmt(row.records, 0), fdate(row.first_date), fdate(row.last_date)])));
  body.push(el('h3', {text: t('database.backups')}));
  if (!panel.backups.length) body.push(el('p', {class: 'stat', text: t('database.no_backups')}));
  panel.backups.forEach(backup => {
    const button = el('button', {class: 'btn', type: 'button', text: t('database.restore')});
    button.addEventListener('click', async () => {
      if (button.dataset.armed !== 'yes') { button.dataset.armed = 'yes'; button.textContent = t('database.restore_confirm'); return; }
      const answer = await call('restore_backup', backup.name);
      if (!answer.ok) return showError(answer.error);
      closeDialog();
      await start();
    });
    body.push(el('div', {class: 'row'}, [el('span', {class: 'stat', text: fmoment(backup.saved_at) + ' · ' + fsize(backup.size_bytes)}), button]));
  });
  openDialog(t('action.database'), body);
}
async function exportCsv(target) {
  const answer = await call('export_csv', state.period, state.nights);
  if (!answer.ok) return showError(answer.error);
  target.textContent = answer.saved ? t('data.saved', {name: answer.file_name}) : '';
}

/* ---------- flow ---------- */
const RENDER = {oxygen: renderOxygen, sleep: renderSleep, heart: renderHeart, activity: renderActivity, relate: renderRelate, data: renderData};
function renderTab() {
  $$('[role=tabpanel]').forEach(panel => { panel.hidden = panel.id !== 'p-' + state.tab; });
  $$('#tabs button').forEach(button => button.setAttribute('aria-selected', String(button.dataset.tab === state.tab)));
  RENDER[state.tab]();
}
async function reload() {
  const answer = await call('dashboard', state.period, state.nights);
  if (!answer.ok) return showError(answer.error);
  state.data = answer;
  renderKpis();
  renderTab();
}
function applyTheme() {
  if (state.theme === 'system') document.documentElement.removeAttribute('data-theme');
  else document.documentElement.setAttribute('data-theme', state.theme);
  readTokens();
}
async function start() {
  const boot = await call('bootstrap');
  if (!boot.ok) return showError(boot.error);
  state.boot = boot; state.texts = boot.texts; state.language = boot.language; state.theme = boot.theme;
  applyTheme();
  applyTexts();
  const language = $('#language');
  language.textContent = '';
  boot.languages.forEach(code => language.appendChild(el('option', {value: code, text: t('language.' + code)})));
  language.value = boot.language;
  fillMetricSelects();
  const hasData = boot.available.nights > 0;
  $('#welcome').hidden = hasData;
  $('#content').hidden = !hasData;
  $('#meta').textContent = hasData ? t('meta.range', {a: fdate(boot.available.first_night), b: fdate(boot.available.last_night), n: boot.available.nights}) : '';
  $('#foot').textContent = t('foot', {version: boot.version});
  if (hasData) await reload();
}
function wire() {
  [['#f-period', 'period'], ['#f-nights', 'nights']].forEach(([selector, key]) => {
    $$(selector + ' button').forEach(button => button.addEventListener('click', () => {
      state[key] = button.dataset.v;
      $$(selector + ' button').forEach(other => other.setAttribute('aria-pressed', String(other === button)));
      reload();
    }));
  });
  $$('#tabs button').forEach(button => button.addEventListener('click', () => { state.tab = button.dataset.tab; renderTab(); }));
  $('#worst-by').addEventListener('change', loadWorst);
  $('#rx').addEventListener('change', event => { state.x = event.target.value; renderRelate(); });
  $('#ry').addEventListener('change', event => { state.y = event.target.value; renderRelate(); });
  $('#swap').addEventListener('click', () => { [state.x, state.y] = [state.y, state.x]; $('#rx').value = state.x; $('#ry').value = state.y; renderRelate(); });
  $('#csv').addEventListener('click', () => exportCsv($('#csv-done')));
  $('#btn-import').addEventListener('click', startImport);
  $('#btn-import-first').addEventListener('click', startImport);
  $('#btn-database').addEventListener('click', showDatabase);
  $('#dialog-close').addEventListener('click', async () => { await call('cancel_import'); closeDialog(); });
  $('#language').addEventListener('change', async event => {
    const answer = await call('set_language', event.target.value);
    if (!answer.ok) return showError(answer.error);
    await start();
  });
  $('#theme').addEventListener('click', async () => {
    const dark = state.theme === 'dark' || (state.theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
    state.theme = dark ? 'light' : 'dark';
    await call('set_theme', state.theme);
    applyTheme();
    if (state.data) { renderKpis(); renderTab(); }
  });
}
function begin() { wire(); start(); }
if (window.pywebview && window.pywebview.api) begin();
else window.addEventListener('pywebviewready', begin);
})();
