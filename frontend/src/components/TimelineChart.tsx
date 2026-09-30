// Master timeline + player stability tracker rendered in ONE ECharts instance
// with two grids that share the same minute category axis. A single dataZoom
// drives both x-axes and the axis pointer is linked, so the crosshair and
// zoom are always synchronized.
import { useEffect, useMemo, useRef, useState } from 'react';
import type { PlayerAnomaly, TimelineDynamics, TimelinePoint } from '../types';
import { useEChart, type EChartsInstance, echarts } from '../echarts';
import { COLORS, ROLE_ORDER, ROLE_SHORT, escapeHtml, humanize, pct, signedGold, signedPct } from '../theme';

interface Props {
  dynamics: TimelineDynamics;
  selectedPlayer: number | null;
  onSelectPlayer: (participantId: number) => void;
  onSelectInflection: (minute: number) => void;
  /** Minute to zoom to; `nonce` re-triggers the zoom for the same minute. */
  focus: { minute: number; nonce: number } | null;
}

const HEAT_COLORS = ['#881337', '#9a3412', '#3f3f46', '#166534', '#22c55e'];
const LANE_H = 24;
const G0_TOP = 40;
const G0_H = 250;
const G1_TOP = G0_TOP + G0_H + 44;
const G1_H = LANE_H * 10;
const SLIDER_TOP = G1_TOP + G1_H + 26;
const CHART_H = SLIDER_TOP + 44;

interface Lane {
  participant_id: number;
  team: 'blue' | 'red';
  label: string;
}

function shapHtml(point: TimelinePoint): string {
  if (!point.shap_summary.length) return '';
  const max = Math.max(...point.shap_summary.map((f) => Math.abs(f.contribution)), 0.01);
  const rows = point.shap_summary
    .map((f) => {
      const pos = f.contribution >= 0;
      const w = (Math.abs(f.contribution) / max) * 50;
      const color = pos ? COLORS.blue : COLORS.red;
      const bar = `<span style="position:absolute;top:0;bottom:0;${pos ? 'left:50%' : 'right:50%'};width:${w}%;background:${color};border-radius:2px"></span>`;
      return `<div style="margin-top:4px"><div style="display:flex;justify-content:space-between;gap:12px"><span>${escapeHtml(f.label)}</span><b style="color:${color}">${signedPct(f.contribution)}</b></div>
        <div style="position:relative;height:6px;background:#334155;border-radius:2px"><span style="position:absolute;left:50%;top:0;bottom:0;width:1px;background:#94a3b8"></span>${bar}</div></div>`;
    })
    .join('');
  return `<div style="margin-top:6px;border-top:1px solid #334155;padding-top:4px"><div style="color:#94a3b8;font-size:11px">Why it moved (SHAP)</div>${rows}</div>`;
}

export function TimelineChart({ dynamics, selectedPlayer, onSelectPlayer, onSelectInflection, focus }: Props) {
  const [hoveredAnomaly, setHoveredAnomaly] = useState<PlayerAnomaly | null>(null);
  const handlers = useRef({ onSelectPlayer, onSelectInflection });
  handlers.current = { onSelectPlayer, onSelectInflection };

  const minutes = useMemo(() => dynamics.timeline.map((t) => t.minute), [dynamics]);
  const idxOf = useMemo(() => {
    const m = new Map<number, number>();
    minutes.forEach((min, i) => m.set(min, i));
    // Nearest index for minutes not exactly on the axis (e.g. fractional window bounds).
    return (minute: number) => {
      const exact = m.get(minute);
      if (exact !== undefined) return exact;
      let best = 0;
      minutes.forEach((min, i) => {
        if (Math.abs(min - minute) < Math.abs(minutes[best] - minute)) best = i;
      });
      return best;
    };
  }, [minutes]);

  const lanes: Lane[] = useMemo(() => {
    return [...dynamics.player_stability]
      .sort((a, b) => (a.team === b.team ? ROLE_ORDER.indexOf(a.role) - ROLE_ORDER.indexOf(b.role) : a.team === 'blue' ? -1 : 1))
      .map((p) => ({
        participant_id: p.participant_id,
        team: p.team,
        label: `${ROLE_SHORT[p.role]} ${p.champion}`,
      }));
  }, [dynamics]);
  const laneIdx = useMemo(() => new Map(lanes.map((l, i) => [l.participant_id, i])), [lanes]);

  const option = useMemo(() => {
    const tl = dynamics.timeline;
    const cats = minutes.map(String);
    const byMinute = new Map(tl.map((t) => [String(t.minute), t]));
    const anomaliesByMinute = new Map<number, PlayerAnomaly[]>();
    dynamics.player_anomalies.forEach((a) => {
      const i = idxOf(a.minute);
      anomaliesByMinute.set(i, [...(anomaliesByMinute.get(i) ?? []), a]);
    });

    const windowArea = (team: 'blue' | 'red') =>
      dynamics.power_windows[team].map((w) => [
        {
          xAxis: idxOf(w.start),
          name: `${team === 'blue' ? 'Blue' : 'Red'} power window`,
          itemStyle: { color: team === 'blue' ? 'rgba(6,182,212,0.10)' : 'rgba(244,63,94,0.10)' },
          label: { color: team === 'blue' ? COLORS.blue : COLORS.red },
        },
        { xAxis: idxOf(w.end) },
      ]);

    const heatData: [number, number, number][] = [];
    dynamics.player_stability.forEach((p) => {
      const y = laneIdx.get(p.participant_id);
      if (y === undefined) return;
      p.scores.forEach((s) => heatData.push([idxOf(s.minute), y, Math.round(s.stability)]));
    });

    const anomalyData = dynamics.player_anomalies
      .filter((a) => laneIdx.has(a.participant_id))
      .map((a) => ({
        value: [idxOf(a.minute), laneIdx.get(a.participant_id) as number],
        anomaly: a,
        symbolSize: a.severity === 'HIGH' ? [22, 14] : a.severity === 'MEDIUM' ? [18, 12] : [14, 10],
      }));

    const tooltipFormatter = (raw: unknown) => {
      const params = (Array.isArray(raw) ? raw : [raw]) as { axisValue?: string | number }[];
      const key = String(params[0]?.axisValue ?? '');
      const p = byMinute.get(key);
      if (!p) return '';
      const s = p.state;
      const i = idxOf(p.minute);
      const anomalies = anomaliesByMinute.get(i) ?? [];
      const anomalyHtml = anomalies.length
        ? `<div style="margin-top:6px;border-top:1px solid #334155;padding-top:4px">${anomalies
            .map((a) => `<div style="color:${COLORS.amber}">▲ ${escapeHtml(a.champion)} · ${humanize(a.anomaly_type)} (${a.severity})</div>`)
            .join('')}</div>`
        : '';
      return `<div style="min-width:220px;max-width:300px;white-space:normal">
        <div style="display:flex;justify-content:space-between"><b>Minute ${p.minute}</b>${p.is_inflection_point ? `<span style="color:${COLORS.amber}">◆ inflection</span>` : ''}</div>
        <div style="margin-top:4px">Blue win prob <b style="color:${COLORS.blue}">${pct(p.win_probability_blue, 1)}</b>
          <span style="color:${p.delta_win_probability >= 0 ? COLORS.blue : COLORS.red}">(${signedPct(p.delta_win_probability)})</span></div>
        <div>Power <span style="color:${COLORS.blue}">${p.team_blue_power_index.toFixed(0)}</span> vs <span style="color:${COLORS.red}">${p.team_red_power_index.toFixed(0)}</span></div>
        <div>Gold <span style="color:${COLORS.blue}">${s.gold_blue.toLocaleString()}</span> / <span style="color:${COLORS.red}">${s.gold_red.toLocaleString()}</span> (${signedGold(s.gold_diff)})</div>
        <div>Items <span style="color:${COLORS.blue}">${s.items_completed_blue}</span> / <span style="color:${COLORS.red}">${s.items_completed_red}</span> · Kills ${s.kills_blue}–${s.kills_red}</div>
        <div>Drakes ${s.dragons_blue}–${s.dragons_red} · Barons ${s.barons_blue}–${s.barons_red} · Towers ${s.towers_blue}–${s.towers_red}</div>
        ${shapHtml(p)}${anomalyHtml}</div>`;
    };

    return {
      backgroundColor: 'transparent',
      animationDuration: 400,
      textStyle: { color: COLORS.text },
      axisPointer: { link: [{ xAxisIndex: 'all' }], label: { backgroundColor: '#334155', color: COLORS.text } },
      tooltip: {
        trigger: 'axis',
        confine: true,
        backgroundColor: 'rgba(15,23,42,0.96)',
        borderColor: '#475569',
        textStyle: { color: COLORS.text, fontSize: 12 },
        axisPointer: { type: 'line', lineStyle: { color: '#94a3b8', type: 'dashed' } },
        formatter: tooltipFormatter,
      },
      grid: [
        { left: 128, right: 24, top: G0_TOP, height: G0_H },
        { left: 128, right: 24, top: G1_TOP, height: G1_H },
      ],
      xAxis: [
        {
          type: 'category', gridIndex: 0, data: cats, boundaryGap: true,
          axisLine: { lineStyle: { color: '#475569' } }, axisLabel: { color: COLORS.muted }, axisTick: { show: false },
        },
        {
          type: 'category', gridIndex: 1, data: cats, boundaryGap: true, name: 'minute', nameLocation: 'end', nameGap: 6,
          nameTextStyle: { color: COLORS.muted }, axisLine: { lineStyle: { color: '#475569' } }, axisLabel: { color: COLORS.muted }, axisTick: { show: false },
        },
      ],
      yAxis: [
        {
          type: 'value', gridIndex: 0, min: 0, max: 100, interval: 25,
          axisLabel: { color: COLORS.muted, formatter: '{value}%' },
          splitLine: { lineStyle: { color: '#1e293b' } },
          name: 'Blue win probability', nameTextStyle: { color: COLORS.muted, align: 'left' },
        },
        {
          type: 'category', gridIndex: 1, data: lanes.map((l) => l.label), inverse: true,
          axisLine: { show: false }, axisTick: { show: false }, splitLine: { show: false },
          axisLabel: {
            formatter: (_v: string, i: number) => {
              const l = lanes[i];
              if (!l) return '';
              const style = `${l.team}${l.participant_id === selectedPlayer ? 'Sel' : ''}`;
              return `{${style}|${l.label}}`;
            },
            rich: {
              blue: { color: COLORS.blue, fontSize: 11 },
              red: { color: COLORS.red, fontSize: 11 },
              blueSel: { color: '#0f172a', backgroundColor: COLORS.blue, fontSize: 11, fontWeight: 'bold', padding: [2, 4], borderRadius: 3 },
              redSel: { color: '#0f172a', backgroundColor: COLORS.red, fontSize: 11, fontWeight: 'bold', padding: [2, 4], borderRadius: 3 },
            },
          },
        },
      ],
      dataZoom: [
        { type: 'inside', xAxisIndex: [0, 1], minValueSpan: 4 },
        {
          type: 'slider', xAxisIndex: [0, 1], top: SLIDER_TOP, height: 20, left: 128, right: 24,
          borderColor: '#334155', backgroundColor: '#0f172a', fillerColor: 'rgba(245,158,11,0.15)',
          handleStyle: { color: COLORS.amber, borderColor: COLORS.amber },
          textStyle: { color: COLORS.muted }, dataBackground: { lineStyle: { color: '#475569' }, areaStyle: { color: '#1e293b' } },
        },
      ],
      visualMap: {
        type: 'continuous', seriesIndex: 3, min: 0, max: 100, show: false, inRange: { color: HEAT_COLORS },
      },
      series: [
        {
          name: 'Blue power index', type: 'line', xAxisIndex: 0, yAxisIndex: 0, smooth: true, symbol: 'none',
          data: tl.map((t) => t.team_blue_power_index),
          lineStyle: { color: COLORS.blue, width: 1, opacity: 0.35 }, itemStyle: { color: COLORS.blue },
          areaStyle: { color: COLORS.blue, opacity: 0.1 }, z: 1,
        },
        {
          name: 'Red power index', type: 'line', xAxisIndex: 0, yAxisIndex: 0, smooth: true, symbol: 'none',
          data: tl.map((t) => t.team_red_power_index),
          lineStyle: { color: COLORS.red, width: 1, opacity: 0.35 }, itemStyle: { color: COLORS.red },
          areaStyle: { color: COLORS.red, opacity: 0.1 }, z: 1,
        },
        {
          name: 'Blue win probability', type: 'line', xAxisIndex: 0, yAxisIndex: 0, smooth: 0.3,
          symbol: 'circle', symbolSize: 5, showSymbol: false,
          data: tl.map((t) => Math.round(t.win_probability_blue * 1000) / 10),
          lineStyle: { width: 3, color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: COLORS.blue }, { offset: 0.5, color: '#e2e8f0' }, { offset: 1, color: COLORS.red },
          ]) },
          itemStyle: { color: '#e2e8f0' }, z: 3,
          markLine: {
            silent: true, symbol: 'none', label: { show: true, formatter: '50%', color: COLORS.muted, position: 'insideEndTop' },
            lineStyle: { color: '#64748b', type: 'dashed', width: 1 }, data: [{ yAxis: 50 }],
          },
          markArea: {
            silent: true,
            label: { position: 'insideTop', fontSize: 10, opacity: 0.8 },
            data: [...windowArea('blue'), ...windowArea('red')],
          },
          markPoint: {
            symbol: 'pin', symbolSize: 36,
            itemStyle: { color: COLORS.amber, borderColor: '#0f172a', borderWidth: 1 },
            label: { color: '#0f172a', fontSize: 9, fontWeight: 'bold', formatter: (p: { data?: { delta?: number } }) => signedPct(p.data?.delta ?? 0, 0) },
            data: dynamics.inflection_points.map((ip) => {
              const i = idxOf(ip.minute);
              return { name: `inflection-${ip.minute}`, coord: [i, tl[i] ? tl[i].win_probability_blue * 100 : 50], delta: ip.delta, minute: ip.minute };
            }),
          },
        },
        {
          name: 'Stability', type: 'heatmap', xAxisIndex: 1, yAxisIndex: 1, data: heatData,
          itemStyle: { borderColor: '#0f172a', borderWidth: 1 },
          emphasis: { itemStyle: { borderColor: '#e2e8f0', borderWidth: 1 } }, z: 1,
        },
        {
          name: 'Anomalies', type: 'scatter', xAxisIndex: 1, yAxisIndex: 1, symbol: 'roundRect', data: anomalyData,
          itemStyle: { color: COLORS.amber, borderColor: '#0f172a', borderWidth: 1.5, shadowBlur: 6, shadowColor: 'rgba(245,158,11,0.6)' },
          emphasis: { scale: 1.4 }, z: 5,
        },
      ],
    } satisfies echarts.EChartsCoreOption;
  }, [dynamics, minutes, idxOf, lanes, laneIdx, selectedPlayer]);

  const onInit = (chart: EChartsInstance) => {
    chart.on('click', (raw) => {
      const p = raw as { componentType?: string; seriesType?: string; data?: unknown; value?: unknown };
      if (p.componentType === 'markPoint') {
        const d = p.data as { minute?: number };
        if (typeof d?.minute === 'number') handlers.current.onSelectInflection(d.minute);
        return;
      }
      if (p.seriesType === 'scatter') {
        const d = p.data as { anomaly?: PlayerAnomaly };
        if (d?.anomaly) handlers.current.onSelectPlayer(d.anomaly.participant_id);
        return;
      }
      if (p.seriesType === 'heatmap') {
        const v = p.value as [number, number, number];
        const lane = lanesRef.current[v[1]];
        if (lane) handlers.current.onSelectPlayer(lane.participant_id);
      }
    });
    chart.on('mouseover', (raw) => {
      const p = raw as { seriesType?: string; data?: { anomaly?: PlayerAnomaly } };
      if (p.seriesType === 'scatter' && p.data?.anomaly) setHoveredAnomaly(p.data.anomaly);
    });
    chart.on('mouseout', (raw) => {
      const p = raw as { seriesType?: string };
      if (p.seriesType === 'scatter') setHoveredAnomaly(null);
    });
  };
  const lanesRef = useRef(lanes);
  lanesRef.current = lanes;

  // Merge (not replace) so selecting a player keeps the current zoom.
  const { ref, chartRef } = useEChart(option, onInit, false);

  // Reset zoom when a different match is loaded.
  useEffect(() => {
    chartRef.current?.dispatchAction({ type: 'dataZoom', start: 0, end: 100 });
  }, [dynamics.match_id, chartRef]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !focus) return;
    const i = idxOf(focus.minute);
    chart.dispatchAction({ type: 'dataZoom', startValue: Math.max(0, i - 4), endValue: Math.min(minutes.length - 1, i + 4) });
    chart.dispatchAction({ type: 'showTip', seriesIndex: 2, dataIndex: i });
  }, [focus, idxOf, minutes.length, chartRef]);

  const resetZoom = () => {
    chartRef.current?.dispatchAction({ type: 'dataZoom', start: 0, end: 100 });
    chartRef.current?.dispatchAction({ type: 'hideTip' });
  };

  const last = dynamics.timeline[dynamics.timeline.length - 1];
  const summary = `Timeline of ${dynamics.duration_min} minutes. Blue win probability ends at ${last ? pct(last.win_probability_blue) : 'n/a'}. ${dynamics.inflection_points.length} inflection points and ${dynamics.player_anomalies.length} player anomalies. Use the inflection cards and scoreboard for keyboard navigation.`;

  return (
    <section aria-labelledby="timeline-title" className="rounded-lg border border-slate-800 bg-slate-900 p-3 text-slate-100">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="timeline-title" className="text-base font-semibold">Match pulse &amp; player stability</h2>
        <div className="flex flex-wrap items-center gap-3 text-xs text-slate-300">
          <span className="flex items-center gap-1"><span className="h-0.5 w-4 bg-slate-200" aria-hidden="true" />Win prob</span>
          <span className="flex items-center gap-1"><span className="h-3 w-4 rounded-sm bg-side-blue/30" aria-hidden="true" />Blue power</span>
          <span className="flex items-center gap-1"><span className="h-3 w-4 rounded-sm bg-side-red/30" aria-hidden="true" />Red power</span>
          <span className="flex items-center gap-1"><span className="h-3 w-3 rotate-45 bg-inflect" aria-hidden="true" />Inflection / anomaly</span>
          <span className="flex items-center gap-1">
            Stability
            <span className="h-2.5 w-16 rounded-sm" style={{ background: `linear-gradient(90deg, ${HEAT_COLORS.join(',')})` }} aria-hidden="true" />
            <span className="text-slate-400">low → high</span>
          </span>
          <button type="button" onClick={resetZoom} className="rounded bg-slate-700 px-2 py-1 font-medium text-slate-100 hover:bg-slate-600">
            Reset zoom
          </button>
        </div>
      </div>
      <div ref={ref} role="img" aria-label={summary} style={{ height: CHART_H }} className="w-full" />
      <p className="min-h-5 text-sm text-amber-200" aria-live="polite">
        {hoveredAnomaly
          ? `▲ ${hoveredAnomaly.champion} (${hoveredAnomaly.team}) · min ${hoveredAnomaly.minute} · ${humanize(hoveredAnomaly.anomaly_type)} · ${hoveredAnomaly.severity}: ${hoveredAnomaly.description}`
          : <span className="text-slate-500">Hover an amber pill for anomaly details · click a lane to select a player · click a pin to inspect an inflection.</span>}
      </p>
    </section>
  );
}
