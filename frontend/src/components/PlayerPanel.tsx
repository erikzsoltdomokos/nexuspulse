import { useMemo } from 'react';
import type { Participant, PlayerAnomaly, PlayerRadar, PlayerStability, RadarMetrics } from '../types';
import { useEChart } from '../echarts';
import { COLORS, ROLE_SHORT, SEVERITY_CLASS, teamColor } from '../theme';
import { useI18n } from '../i18n';

interface Props {
  participantId: number | null;
  participant: Participant | undefined;
  stability: PlayerStability | undefined;
  radar: PlayerRadar | undefined;
  teamRadar: PlayerRadar[];
  anomalies: PlayerAnomaly[];
  onFocusMinute: (minute: number) => void;
}

const AXES: (keyof RadarMetrics)[] = ['farming', 'fighting', 'vision', 'objectives', 'survival', 'stability'];

export function PlayerPanel({ participantId, participant, stability, radar, teamRadar, anomalies, onFocusMinute }: Props) {
  const { t, locale, team: teamLabel, anomalyType, severity, radarAxis, anomalyDescription } = useI18n();
  const team = participant?.team ?? stability?.team ?? 'blue';
  const color = teamColor(team);
  const champion = participant?.champion ?? stability?.champion ?? '—';
  const role = participant?.role ?? stability?.role;

  const option = useMemo(() => {
    if (!radar) return null;
    const avg = AXES.map((k) => (teamRadar.length ? Math.round(teamRadar.reduce((a, r) => a + r.metrics[k], 0) / teamRadar.length) : 0));
    return {
      backgroundColor: 'transparent',
      tooltip: { trigger: 'item', backgroundColor: 'rgba(15,23,42,0.96)', borderColor: '#475569', textStyle: { color: COLORS.text } },
      radar: {
        indicator: AXES.map((k) => ({ name: radarAxis(k), max: 100 })),
        radius: '68%',
        axisName: { color: COLORS.text, fontSize: 11 },
        splitLine: { lineStyle: { color: '#334155' } },
        splitArea: { areaStyle: { color: ['#0f172a', '#131c31'] } },
        axisLine: { lineStyle: { color: '#334155' } },
      },
      series: [
        {
          type: 'radar',
          data: [
            {
              name: t('teamAverage'),
              value: avg,
              symbol: 'none',
              lineStyle: { color: '#94a3b8', type: 'dashed', width: 1 },
              areaStyle: { color: 'rgba(148,163,184,0.08)' },
            },
            {
              name: champion,
              value: AXES.map((k) => radar.metrics[k]),
              lineStyle: { color, width: 2 },
              itemStyle: { color },
              areaStyle: { color, opacity: 0.25 },
            },
          ],
        },
      ],
    };
  }, [radar, teamRadar, champion, color, t, radarAxis]);

  const { ref } = useEChart(option);
  const avgStab = stability?.scores.length ? Math.round(stability.scores.reduce((a, s) => a + s.stability, 0) / stability.scores.length) : null;


  return (
    <section aria-labelledby="player-title" className="grid gap-4 rounded-lg border border-slate-800 bg-slate-900 p-3 text-slate-100 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <div>
        <h2 id="player-title" className="text-base font-semibold">
          <span style={{ color }}>{champion}</span>
          <span className="text-sm font-normal text-slate-400">
            {' '}· {teamLabel(team)} {role ? ROLE_SHORT[role] : ''}
            {participant ? ` · ${participant.riot_id}` : ''}
          </span>
        </h2>
        {participant && (
          <dl className="mt-1 flex flex-wrap gap-x-4 text-xs text-slate-300">
            <div><dt className="inline text-slate-500">{t('colKda')} </dt><dd className="inline">{participant.kills}/{participant.deaths}/{participant.assists}</dd></div>
            <div><dt className="inline text-slate-500">{t('damage')} </dt><dd className="inline">{participant.damage.toLocaleString(locale)}</dd></div>
            <div><dt className="inline text-slate-500">{t('vision')} </dt><dd className="inline">{participant.vision_score}</dd></div>
            {avgStab !== null && <div><dt className="inline text-slate-500">{t('avgStability')} </dt><dd className="inline">{avgStab}</dd></div>}
          </dl>
        )}
        {/* The chart container stays mounted so the ECharts instance survives player changes. */}
        <div
          ref={ref}
          className={radar ? 'h-72 w-full' : 'hidden'}
          role="img"
          aria-label={radar ? t('radarAria', { c: champion, metrics: AXES.map((k) => `${radarAxis(k)} ${radar.metrics[k]}`).join(', ') }) : t('noRadarData')}
        />
        {!radar && <p className="mt-4 text-sm text-slate-400">{participantId === null ? t('selectPlayerHint') : t('noRadarMetrics')}</p>}
      </div>

      <div>
        <h3 className="mb-2 text-sm font-semibold">
          {t('anomalies')} <span className="font-normal text-slate-400">({anomalies.length})</span>
        </h3>
        {anomalies.length === 0 ? (
          <p className="text-sm text-slate-400">{t('noAnomalies')}</p>
        ) : (
          <ul className="space-y-2">
            {[...anomalies]
              .sort((a, b) => a.minute - b.minute)
              .map((a) => (
                <li key={`${a.minute}-${a.anomaly_type}`}>
                  <button
                    type="button"
                    onClick={() => onFocusMinute(a.minute)}
                    className="w-full rounded-md border border-slate-700 bg-slate-800 p-2 text-left hover:bg-slate-700"
                    aria-label={t('anomalyAria', { m: a.minute, type: anomalyType(a.anomaly_type), sev: severity(a.severity), desc: anomalyDescription(a.description) })}
                  >
                    <div className="flex flex-wrap items-center gap-2 text-sm">
                      <span className="font-semibold text-inflect">{a.minute}:00</span>
                      <span className="text-slate-100">{anomalyType(a.anomaly_type)}</span>
                      <span className={`rounded border px-1.5 py-0.5 text-[10px] font-bold ${SEVERITY_CLASS[a.severity]}`}>{severity(a.severity)}</span>
                      <span className="ml-auto text-xs tabular-nums text-slate-400">{t('scoreN', { s: a.score.toFixed(2) })}</span>
                    </div>
                    <p className="mt-1 text-xs text-slate-300">{anomalyDescription(a.description)}</p>
                  </button>
                </li>
              ))}
          </ul>
        )}
      </div>
    </section>
  );
}
