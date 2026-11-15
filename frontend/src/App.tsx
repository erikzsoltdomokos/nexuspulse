import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ApiError, api, loadDemo } from './api';
import type { CollectResult, Health, MatchSummary, Overview, TimelineDynamics } from './types';
import { Header } from './components/Header';
import { OverviewStrip } from './components/OverviewStrip';
import { TimelineChart } from './components/TimelineChart';
import { InflectionPanel } from './components/InflectionPanel';
import { PlayerPanel } from './components/PlayerPanel';
import { useI18n } from './i18n';

type HealthState = 'loading' | 'ok' | 'down';

export default function App() {
  const i18n = useI18n();
  const { t } = i18n;
  // Callbacks read the current language through a ref so they stay referentially stable.
  const i18nRef = useRef(i18n);
  i18nRef.current = i18n;
  const errMsg = (err: unknown) => i18nRef.current.errorText(err instanceof Error ? err.message : String(err));
  const [health, setHealth] = useState<Health | null>(null);
  const [healthState, setHealthState] = useState<HealthState>('loading');
  const [matches, setMatches] = useState<MatchSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [dynamics, setDynamics] = useState<TimelineDynamics | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [demo, setDemo] = useState(false);
  const [selectedPlayer, setSelectedPlayer] = useState<number | null>(null);
  const [activeInflection, setActiveInflection] = useState<number | null>(null);
  const [focus, setFocus] = useState<{ minute: number; nonce: number } | null>(null);

  const refreshMatches = useCallback(async () => {
    const res = await api.matches();
    const sorted = [...res.matches].sort((a, b) => b.game_creation - a.game_creation);
    setMatches(sorted);
    return sorted;
  }, []);

  const checkBackend = useCallback(async () => {
    setHealthState('loading');
    try {
      const h = await api.health();
      setHealth(h);
      setHealthState('ok');
      await refreshMatches();
    } catch (err) {
      setHealth(null);
      setHealthState(err instanceof ApiError && !err.unreachable ? 'ok' : 'down');
      if (!(err instanceof ApiError && err.unreachable)) setError(errMsg(err));
    }
  }, [refreshMatches]);

  useEffect(() => {
    void checkBackend();
  }, [checkBackend]);

  const applyMatch = (o: Overview | null, d: TimelineDynamics) => {
    setOverview(o);
    setDynamics(d);
    setActiveInflection(null);
    setFocus(null);
    // Default to the player with the most severe anomaly, else participant 1.
    const worst = [...d.player_anomalies].sort((a, b) => b.score - a.score)[0];
    setSelectedPlayer(worst?.participant_id ?? d.player_stability[0]?.participant_id ?? null);
  };

  const selectMatch = useCallback(async (id: string) => {
    setSelectedId(id);
    setDemo(false);
    setLoading(true);
    setError(null);
    try {
      const [o, d] = await Promise.all([api.overview(id), api.dynamics(id)]);
      applyMatch(o, d);
    } catch (err) {
      setError(i18nRef.current.t('couldNotLoad', { id, msg: errMsg(err) }));
      if (err instanceof ApiError && err.unreachable) setHealthState('down');
    } finally {
      setLoading(false);
    }
  }, []);

  // Auto-open a match once the list arrives: ?match=<id> from the URL, else the newest one.
  const autoPicked = useRef(false);
  useEffect(() => {
    if (autoPicked.current || demo || selectedId || matches.length === 0) return;
    autoPicked.current = true;
    const wanted = new URLSearchParams(window.location.search).get('match');
    const pick = wanted || matches[0].match_id;
    void selectMatch(pick);
  }, [matches, demo, selectedId, selectMatch]);

  const loadDemoData = async () => {
    setLoading(true);
    setError(null);
    try {
      const { overview: o, dynamics: d } = await loadDemo();
      setDemo(true);
      setSelectedId(null);
      applyMatch(o, d);
    } catch (err) {
      setError(t('couldNotLoadDemo', { msg: errMsg(err) }));
    } finally {
      setLoading(false);
    }
  };

  const collectMatch = async (id: string): Promise<CollectResult> => {
    const r = await api.collectMatch(id);
    if (r.state !== 'error') {
      await refreshMatches();
      void selectMatch(r.match_id);
    }
    return r;
  };

  const collectPlayer = async (name: string, tag: string, count: number) => {
    const r = await api.collectPlayer(name, tag, count);
    await refreshMatches();
    const firstOk = r.results.find((x) => x.state !== 'error');
    if (firstOk) void selectMatch(firstOk.match_id);
    return r.results;
  };

  const focusMinute = (minute: number) => setFocus({ minute, nonce: Date.now() });
  const selectInflection = (minute: number) => {
    setActiveInflection(minute);
    focusMinute(minute);
  };

  const playerData = useMemo(() => {
    if (!dynamics || selectedPlayer === null) return null;
    const stability = dynamics.player_stability.find((p) => p.participant_id === selectedPlayer);
    const participant = overview?.participants.find((p) => p.participant_id === selectedPlayer);
    const team = participant?.team ?? stability?.team;
    const teamIds = new Set(dynamics.player_stability.filter((p) => p.team === team).map((p) => p.participant_id));
    return {
      stability,
      participant,
      radar: dynamics.player_radar.find((r) => r.participant_id === selectedPlayer),
      teamRadar: dynamics.player_radar.filter((r) => teamIds.has(r.participant_id)),
      anomalies: dynamics.player_anomalies.filter((a) => a.participant_id === selectedPlayer),
    };
  }, [dynamics, overview, selectedPlayer]);

  return (
    <div className="min-h-screen bg-app text-slate-100">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:rounded focus:bg-amber-500 focus:px-3 focus:py-1 focus:text-slate-950">
        {t('skipToContent')}
      </a>
      <Header
        health={health}
        healthState={healthState}
        matches={matches}
        selectedId={selectedId}
        demo={demo}
        onSelect={(id) => void selectMatch(id)}
        onCollectMatch={collectMatch}
        onCollectPlayer={collectPlayer}
      />

      <main id="main" className="mx-auto max-w-[1600px] space-y-4 px-4 py-4">
        {healthState === 'down' && !demo && (
          <div role="alert" className="flex flex-wrap items-center gap-3 rounded-lg border border-amber-600 bg-amber-950 px-4 py-3 text-amber-100">
            <span className="font-semibold">{t('backendDown')}</span>
            <span className="text-sm text-amber-200">{t('backendDownDetail')}</span>
            <div className="ml-auto flex gap-2">
              <button type="button" onClick={() => void checkBackend()} className="rounded bg-slate-800 px-3 py-1.5 text-sm font-medium text-slate-100 hover:bg-slate-700">
                {t('retry')}
              </button>
              <button type="button" onClick={() => void loadDemoData()} className="rounded bg-amber-500 px-3 py-1.5 text-sm font-semibold text-slate-950 hover:bg-amber-400">
                {t('loadDemo')}
              </button>
            </div>
          </div>
        )}

        {error && (
          <div role="alert" className="flex items-center gap-3 rounded-lg border border-rose-700 bg-rose-950 px-4 py-3 text-sm text-rose-100">
            <span>{error}</span>
            <button type="button" onClick={() => setError(null)} className="ml-auto rounded bg-rose-900 px-2 py-1 text-xs text-rose-50 hover:bg-rose-800" aria-label={t('dismissError')}>
              {t('dismiss')}
            </button>
          </div>
        )}

        {loading && (
          <div role="status" aria-live="polite" className="flex items-center gap-3 rounded-lg bg-slate-900 px-4 py-3 text-slate-300">
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-600 border-t-cyan-400" aria-hidden="true" />
            {t('loadingAnalysis')}
          </div>
        )}

        {!dynamics && !loading && (
          <div className="rounded-lg border border-dashed border-slate-700 bg-slate-900 px-6 py-12 text-center text-slate-300">
            <p className="text-lg font-semibold text-slate-100">{t('noMatchLoaded')}</p>
            <p className="mt-1 text-sm">{t('noMatchHint')}</p>
            <button type="button" onClick={() => void loadDemoData()} className="mt-4 rounded bg-amber-500 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-amber-400">
              {t('loadDemo')}
            </button>
          </div>
        )}

        {dynamics && (
          <>
            {overview && <OverviewStrip overview={overview} selectedId={selectedPlayer} onSelect={setSelectedPlayer} />}
            <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
              <TimelineChart
                dynamics={dynamics}
                selectedPlayer={selectedPlayer}
                onSelectPlayer={setSelectedPlayer}
                onSelectInflection={selectInflection}
                focus={focus}
              />
              <InflectionPanel
                inflections={dynamics.inflection_points}
                timeline={dynamics.timeline}
                activeMinute={activeInflection}
                onSelect={selectInflection}
                onClear={() => setActiveInflection(null)}
              />
            </div>
            <PlayerPanel
              participantId={selectedPlayer}
              participant={playerData?.participant}
              stability={playerData?.stability}
              radar={playerData?.radar}
              teamRadar={playerData?.teamRadar ?? []}
              anomalies={playerData?.anomalies ?? []}
              onFocusMinute={focusMinute}
            />
          </>
        )}
      </main>
    </div>
  );
}
