import type { Overview, Participant, Team } from '../types';
import { ROLE_ORDER, ROLE_SHORT, fmtGold } from '../theme';
import { useI18n } from '../i18n';

interface Props {
  overview: Overview;
  selectedId: number | null;
  onSelect: (participantId: number) => void;
}

function TeamTable({ team, players, won, selectedId, onSelect }: { team: Team; players: Participant[]; won: boolean; selectedId: number | null; onSelect: (id: number) => void }) {
  const { t, team: teamLabel } = useI18n();
  const accent = team === 'blue' ? 'border-side-blue text-side-blue' : 'border-side-red text-side-red';
  const k = players.reduce((a, p) => a + p.kills, 0);
  const g = players.reduce((a, p) => a + p.gold, 0);
  return (
    <section className={`rounded-lg border-t-4 bg-slate-800 text-slate-100 ${accent.split(' ')[0]}`} aria-label={t('teamAria', { team: teamLabel(team) })}>
      <div className="flex items-center justify-between px-3 py-2">
        <h3 className={`text-sm font-semibold uppercase tracking-wide ${accent.split(' ')[1]}`}>
          {t('teamSide', { team: teamLabel(team) })} <span className="font-normal text-slate-400">· {t('killsGold', { k, g: fmtGold(g) })}</span>
        </h3>
        {won ? (
          <span className="rounded bg-emerald-500 px-2 py-0.5 text-xs font-bold text-slate-950">{t('victory')}</span>
        ) : (
          <span className="rounded bg-slate-700 px-2 py-0.5 text-xs font-semibold text-slate-300">{t('defeat')}</span>
        )}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <caption className="sr-only">{t('scoreboardCaption', { team: teamLabel(team) })}</caption>
          <thead className="text-xs text-slate-400">
            <tr>
              <th scope="col" className="px-3 py-1 text-left font-medium">{t('colRole')}</th>
              <th scope="col" className="px-3 py-1 text-left font-medium">{t('colPlayer')}</th>
              <th scope="col" className="px-3 py-1 text-right font-medium">{t('colKda')}</th>
              <th scope="col" className="px-3 py-1 text-right font-medium">{t('colCs')}</th>
              <th scope="col" className="px-3 py-1 text-right font-medium">{t('colGold')}</th>
            </tr>
          </thead>
          <tbody>
            {players.map((p) => {
              const selected = p.participant_id === selectedId;
              return (
                <tr
                  key={p.participant_id}
                  tabIndex={0}
                  aria-selected={selected}
                  onClick={() => onSelect(p.participant_id)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      onSelect(p.participant_id);
                    }
                  }}
                  className={`cursor-pointer border-t border-slate-700 ${selected ? 'bg-slate-700' : 'hover:bg-slate-700/60'}`}
                >
                  <td className="px-3 py-1.5 text-xs text-slate-400">{ROLE_SHORT[p.role]}</td>
                  <td className="px-3 py-1.5">
                    <div className="font-medium text-slate-100">{p.champion}</div>
                    <div className="truncate text-xs text-slate-400">{p.riot_id}</div>
                  </td>
                  <td className="px-3 py-1.5 text-right tabular-nums">
                    {p.kills}/<span className="text-rose-300">{p.deaths}</span>/{p.assists}
                    <div className="text-xs text-slate-400">{((p.kills + p.assists) / Math.max(1, p.deaths)).toFixed(2)}</div>
                  </td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{p.cs}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums text-amber-200">{fmtGold(p.gold)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function OverviewStrip({ overview, selectedId, onSelect }: Props) {
  const { t, team: teamLabel } = useI18n();
  const byTeam = (t: Team) =>
    overview.participants
      .filter((p) => p.team === t)
      .sort((a, b) => ROLE_ORDER.indexOf(a.role) - ROLE_ORDER.indexOf(b.role));
  return (
    <section aria-labelledby="overview-title" className="space-y-2">
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <h2 id="overview-title" className="text-lg font-semibold text-slate-100">{overview.match_id}</h2>
        <span className={`rounded px-2 py-0.5 text-xs font-bold text-slate-950 ${overview.winner === 'blue' ? 'bg-side-blue' : 'bg-side-red'}`}>
          {t('teamWin', { team: teamLabel(overview.winner) })}
        </span>
        <span className="text-sm text-slate-400">
          {Math.floor(overview.duration_min)}:{String(Math.round((overview.duration_min % 1) * 60)).padStart(2, '0')} · {t('patchQueue', { patch: overview.game_version.split('.').slice(0, 2).join('.'), queue: overview.queue_id })}
        </span>
      </div>
      <div className="grid gap-3 lg:grid-cols-2">
        <TeamTable team="blue" players={byTeam('blue')} won={overview.winner === 'blue'} selectedId={selectedId} onSelect={onSelect} />
        <TeamTable team="red" players={byTeam('red')} won={overview.winner === 'red'} selectedId={selectedId} onSelect={onSelect} />
      </div>
    </section>
  );
}
