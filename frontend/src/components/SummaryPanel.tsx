import { Fragment, type ReactNode } from 'react';
import type { MatchStory, SummaryDriver, SummaryPlayer, SummaryReason, Team } from '../types';
import { useI18n, type TKey } from '../i18n';

interface Props {
  story: MatchStory;
  onFocusMinute: (minute: number) => void;
}

/** Replace {name} placeholders in a template with React nodes. */
function rich(template: string, vars: Record<string, ReactNode>): ReactNode {
  return template.split(/(\{\w+\})/g).map((part, i) => {
    const m = part.match(/^\{(\w+)\}$/);
    return <Fragment key={i}>{m && m[1] in vars ? vars[m[1]] : part}</Fragment>;
  });
}

/** Hungarian definite article before a written number: "az" for 1, 5, 50-59, otherwise "a". */
const huArticle = (n: number) => (n === 1 || String(n).startsWith('5') ? 'az' : 'a');
const pct = (p: number) => `${Math.round(p * 100)}%`;
const signedPct = (d: number) => `${d >= 0 ? '+' : '−'}${Math.round(Math.abs(d) * 100)}%`;
const shortName = (riotId: string) => riotId.split('#')[0];
const sideClass = (team: Team) => (team === 'blue' ? 'text-side-blue' : 'text-side-red');

const COMP_KEY: Record<keyof SummaryPlayer['components'], TKey> = {
  kda: 'compKda',
  economy: 'compEconomy',
  stability: 'compStability',
  composure: 'compComposure',
  lane: 'compLane',
};

export function SummaryPanel({ story, onFocusMinute }: Props) {
  const { t, raw, lang, team: teamLabel, feature, locale } = useI18n();
  const hu = lang === 'hu';

  const TeamName = ({ team }: { team: Team }) => (
    <span className={`font-semibold ${sideClass(team)}`}>{hu ? teamLabel(team).toLowerCase() : teamLabel(team)}</span>
  );
  // Sentence-initial team name (EN templates start with it).
  const teamNode = (team: Team) => <TeamName team={team} />;

  const MinBtn = ({ m, dot = false }: { m: number; dot?: boolean }) => (
    <button
      type="button"
      onClick={() => onFocusMinute(m)}
      aria-label={t('zoomTo', { m })}
      className="rounded px-0.5 font-semibold text-amber-300 underline decoration-dotted underline-offset-2 hover:bg-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-400"
    >
      {m}
      {dot ? '.' : ''}
    </button>
  );
  /** Minute vars for both languages: m = "26", mm = "26." (HU), am / Am = "a 26." / "A 26." (HU). */
  const minuteVars = (m: number, prefix = '') => ({
    [`${prefix}m`]: <MinBtn m={m} />,
    [`${prefix}mm`]: <MinBtn m={m} dot />,
    [`${prefix}am`]: (
      <>
        {huArticle(m)} <MinBtn m={m} dot />
      </>
    ),
    [`${prefix}Am`]: (
      <>
        {huArticle(m).replace(/^a/, 'A')} <MinBtn m={m} dot />
      </>
    ),
  });

  const players = new Map(story.players.map((p) => [p.participant_id, p]));
  const PlayerName = ({ id }: { id: number | null }) => {
    const p = id !== null ? players.get(id) : undefined;
    if (!p) return <span>?</span>;
    return (
      <span>
        <span className={`font-semibold ${sideClass(p.team)}`}>{shortName(p.riot_id)}</span>{' '}
        <span className="text-slate-400">({p.champion})</span>
      </span>
    );
  };

  const drivers = (list: SummaryDriver[]) =>
    list.map((f) => `${feature(f)} (+${Math.round(f.contribution * 100)}%)`).join(', ');
  const minuteList = (mins: number[]) => (
    <>
      {mins.map((m, i) => (
        <Fragment key={m}>
          {i > 0 && ', '}
          <MinBtn m={m} dot={hu} />
        </Fragment>
      ))}
    </>
  );

  const { outcome, decisive_moment: dm, point_of_no_return: pnr, loser_peak: lp, throw_window: tw } = story;
  const { winner, loser } = outcome;
  const sentences: ReactNode[] = [];

  sentences.push(rich(raw('sumOutcome'), { winner: teamNode(winner), d: outcome.duration_min }));
  if (dm) {
    sentences.push(
      <>
        {rich(raw('sumDecisive'), { ...minuteVars(dm.minute), winner: teamNode(winner), from: pct(dm.p_before), to: pct(dm.p_after) })}
        {dm.drivers.length > 0 && <> {t('sumDrivers', { list: drivers(dm.drivers) })}</>}
      </>,
    );
  }
  sentences.push(pnr ? rich(raw('sumPnr'), { ...minuteVars(pnr.minute), winner: teamNode(winner) }) : t('sumNoPnr'));
  if (lp) {
    sentences.push(
      rich(raw(lp.could_have_won ? 'sumPeakHigh' : 'sumPeakLow'), { ...minuteVars(lp.minute), loser: teamNode(loser), p: pct(lp.p) }),
    );
  }
  if (tw) {
    const drops = tw.drops.map((d, i) => (
      <Fragment key={d.minute}>
        {i > 0 && ', '}
        {rich(raw('sumDropItem'), { ...minuteVars(d.minute), d: signedPct(d.delta), drivers: drivers(d.drivers) || t('diffuseChange') })}
      </Fragment>
    ));
    sentences.push(
      <>
        {rich(raw('sumThrow'), {
          s: <MinBtn m={tw.start} />,
          e: <MinBtn m={tw.end} />,
          as: minuteVars(tw.start).am,
          ae: minuteVars(tw.end).am,
          loser: teamNode(loser),
          from: pct(tw.p_start),
          to: pct(tw.p_end),
        })}
        {tw.drops.length > 0 && <> {rich(raw('sumDrops'), { list: <>{drops}</> })}</>}
      </>,
    );
  }

  const power: ReactNode[] = (['blue', 'red'] as Team[]).map((side) => {
    const w = story.power_windows[side];
    if (!w) return rich(raw('sumPowerNone'), { team: teamNode(side) });
    const range = (
      <>
        {hu && `${huArticle(w.start)} `}
        <MinBtn m={w.start} />–<MinBtn m={w.end} dot={hu} />
      </>
    );
    return rich(raw('sumPower'), { team: teamNode(side), range, idx: w.mean_index.toLocaleString(locale) });
  });
  const lw = story.power_windows.loser_window;
  if (lw) power.push(rich(raw(lw.lost ? 'sumLoserWindowLost' : 'sumLoserWindowGained'), { loser: teamNode(loser), d: signedPct(lw.delta) }));

  const fmtRating = (r: number) => Math.round(r);
  const shpb = story.should_have_performed_better;
  const reasonNode = (r: SummaryReason): ReactNode => {
    switch (r.code) {
      case 'DEATHS':
        return t('rDeaths', { n: r.deaths });
      case 'LANE_GOLD':
        return rich(raw('rLane'), {
          g: Math.abs(r.diff).toLocaleString(locale),
          opp: r.opponent ?? '?',
          ...minuteVars(r.minute),
        });
      case 'TILT':
        return rich(raw('rTilt'), { list: minuteList(r.minutes) });
      case 'LOW_STABILITY':
        return t('rStab', { s: Math.round(r.mean) });
      case 'LOW_DAMAGE':
        return t('rDmg', { p: pct(r.share) });
      case 'WEAKEST_COMPONENT':
        return t('rWeak', { c: t(COMP_KEY[r.component]) });
    }
  };

  const mvp = story.mvp !== null ? players.get(story.mvp) : undefined;
  const best = story.loser_best !== null ? players.get(story.loser_best) : undefined;

  return (
    <section aria-labelledby="summary-title" className="rounded-lg bg-slate-900 p-4 text-slate-200">
      <h2 id="summary-title" className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-300">
        {t('sumTitle')}
      </h2>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <div className="space-y-2 text-sm leading-relaxed">
          {sentences.map((s, i) => (
            <p key={i}>{s}</p>
          ))}
          <p className="text-slate-300">
            {power.map((s, i) => (
              <Fragment key={i}>
                {i > 0 && ' '}
                {s}
              </Fragment>
            ))}
          </p>
        </div>
        <div className="space-y-2 text-sm leading-relaxed">
          {mvp && <p>{rich(raw('sumMvp'), { player: <PlayerName id={mvp.participant_id} />, r: fmtRating(mvp.rating) })}</p>}
          {best && <p>{rich(raw('sumLoserBest'), { player: <PlayerName id={best.participant_id} />, r: fmtRating(best.rating) })}</p>}
          {shpb && (
            <div role="note" className="rounded-md border border-amber-600 bg-amber-950/60 px-3 py-2 text-amber-100">
              <p className="text-xs font-bold uppercase tracking-wide text-amber-300">{t('sumShpbTitle')}</p>
              <p className="mt-1">{rich(raw('sumShpb'), { player: <PlayerName id={shpb.participant_id} />, r: fmtRating(shpb.rating) })}</p>
              <p className="mt-1">
                {rich(raw('sumReasons'), {
                  list: (
                    <>
                      {shpb.reasons.map((r, i) => (
                        <Fragment key={i}>
                          {i > 0 && '; '}
                          {reasonNode(r)}
                        </Fragment>
                      ))}
                    </>
                  ),
                })}
              </p>
            </div>
          )}
          <p className="text-xs text-slate-400">{t('sumRatingNote')}</p>
        </div>
      </div>
    </section>
  );
}
