import { useState, type FormEvent } from 'react';
import type { CollectResult, Health, MatchSummary } from '../types';
import { useI18n } from '../i18n';

interface Props {
  health: Health | null;
  healthState: 'loading' | 'ok' | 'down';
  matches: MatchSummary[];
  selectedId: string | null;
  demo: boolean;
  onSelect: (id: string) => void;
  onCollectMatch: (id: string) => Promise<CollectResult>;
  onCollectPlayer: (name: string, tag: string, count: number) => Promise<CollectResult[]>;
}

const stateClass: Record<CollectResult['state'], string> = {
  cached: 'text-slate-300',
  ingested: 'text-emerald-300',
  error: 'text-rose-300',
};

export function Header({ health, healthState, matches, selectedId, demo, onSelect, onCollectMatch, onCollectPlayer }: Props) {
  const { t, lang, toggleLang, locale, team, collectState, modelName, errorText } = useI18n();
  const [matchInput, setMatchInput] = useState('');
  const [riotId, setRiotId] = useState('');
  const [count, setCount] = useState(5);
  const [busy, setBusy] = useState<'match' | 'player' | null>(null);
  const [message, setMessage] = useState<{ tone: 'ok' | 'error'; text: string } | null>(null);
  const [results, setResults] = useState<CollectResult[]>([]);

  const collectMatch = async (e: FormEvent) => {
    e.preventDefault();
    const id = matchInput.trim();
    if (!id) return;
    setBusy('match');
    setMessage(null);
    setResults([]);
    try {
      const r = await onCollectMatch(id);
      setMessage({ tone: r.state === 'error' ? 'error' : 'ok', text: `${r.match_id}: ${collectState(r.state)}${r.detail ? ` — ${r.detail}` : ''}` });
      if (r.state !== 'error') setMatchInput('');
    } catch (err) {
      setMessage({ tone: 'error', text: errorText(err instanceof Error ? err.message : String(err)) });
    } finally {
      setBusy(null);
    }
  };

  const collectPlayer = async (e: FormEvent) => {
    e.preventDefault();
    const [name, tag] = riotId.split('#').map((s) => s.trim());
    if (!name || !tag) {
      setMessage({ tone: 'error', text: t('enterRiotId') });
      return;
    }
    setBusy('player');
    setMessage(null);
    setResults([]);
    try {
      const r = await onCollectPlayer(name, tag, count);
      const errors = r.filter((x) => x.state === 'error').length;
      setResults(r);
      setMessage({ tone: errors ? 'error' : 'ok', text: t('playerProcessed', { n: r.length, id: `${name}#${tag}`, failed: errors ? t('failedSuffix', { n: errors }) : '' }) });
    } catch (err) {
      setMessage({ tone: 'error', text: errorText(err instanceof Error ? err.message : String(err)) });
    } finally {
      setBusy(null);
    }
  };

  const healthDot = healthState === 'ok' ? 'bg-emerald-400' : healthState === 'down' ? 'bg-rose-500' : 'bg-slate-500 animate-pulse';
  const healthText =
    healthState === 'ok'
      ? `${t('apiOnline', { models: health ? Object.entries(health.models).filter(([, v]) => v).map(([k]) => modelName(k)).join(', ') || t('modelsNone') : '—' })}${health && !health.riot_key_configured ? ` · ${t('noRiotKey')}` : ''}`
      : healthState === 'down'
        ? t('apiOffline')
        : t('checkingApi');
  const collectDisabled = healthState !== 'ok' || busy !== null;
  const inputCls =
    'rounded-md border border-slate-600 bg-slate-900 px-2.5 py-1.5 text-sm text-slate-100 placeholder:text-slate-500 focus:border-cyan-500 disabled:opacity-50';
  const btnCls =
    'rounded-md bg-slate-700 px-3 py-1.5 text-sm font-medium text-slate-100 hover:bg-slate-600 disabled:cursor-not-allowed disabled:opacity-50';

  return (
    <header className="border-b border-slate-800 bg-slate-950 text-slate-100">
      <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-bold tracking-tight">
            <span className="text-side-blue">Nexus</span>
            <span className="text-side-red">Pulse</span>
          </h1>
          <span className="flex items-center gap-2 rounded-full bg-slate-800 px-2.5 py-1 text-xs text-slate-300" role="status" aria-live="polite">
            <span className={`h-2 w-2 rounded-full ${healthDot}`} aria-hidden="true" />
            {healthText}
          </span>
          {demo && <span className="rounded bg-amber-500 px-2 py-0.5 text-xs font-semibold text-slate-950">{t('demoBadge')}</span>}
          <button
            type="button"
            onClick={toggleLang}
            className="rounded-md border border-slate-700 bg-slate-800 px-2 py-1 text-xs font-semibold text-slate-400 hover:bg-slate-700"
            aria-label={t('langToggleAria')}
            title={t('langToggleAria')}
          >
            <span className={lang === 'hu' ? 'text-slate-100' : ''}>HU</span>
            <span aria-hidden="true"> / </span>
            <span className={lang === 'en' ? 'text-slate-100' : ''}>EN</span>
          </button>
        </div>

        <label className="flex items-center gap-2 text-sm text-slate-300">
          <span>{t('matchLabel')}</span>
          <select
            className={`${inputCls} min-w-64`}
            value={selectedId ?? ''}
            onChange={(e) => e.target.value && onSelect(e.target.value)}
            disabled={matches.length === 0}
            aria-label={t('selectMatchAria')}
          >
            <option value="">{matches.length ? t('selectMatch') : t('noMatchesStored')}</option>
            {/* A match opened via ?match= may be older than the newest-N list; still show it as selected. */}
            {selectedId && !matches.some((m) => m.match_id === selectedId) && <option value={selectedId}>{selectedId}</option>}
            {matches.map((m) => (
              <option key={m.match_id} value={m.match_id}>
                {m.match_id} · {new Date(m.game_creation).toLocaleDateString(locale)} · {t('minutesShort', { n: Math.round(m.duration_min) })} · {t('teamWin', { team: team(m.winner) })}
                {m.source === 'synthetic' ? ` · ${t('synthetic')}` : ''}
              </option>
            ))}
          </select>
        </label>

        <form onSubmit={collectMatch} className="flex items-center gap-2" aria-label={t('collectMatchFormAria')}>
          <input
            className={`${inputCls} w-44`}
            placeholder="EUW1_1234567890"
            value={matchInput}
            onChange={(e) => setMatchInput(e.target.value)}
            aria-label={t('matchIdAria')}
            disabled={collectDisabled}
          />
          <button type="submit" className={btnCls} disabled={collectDisabled || !matchInput.trim()}>
            {busy === 'match' ? t('collecting') : t('collectMatch')}
          </button>
        </form>

        <form onSubmit={collectPlayer} className="flex items-center gap-2" aria-label={t('collectPlayerFormAria')}>
          <input
            className={`${inputCls} w-40`}
            placeholder={t('riotIdPlaceholder')}
            value={riotId}
            onChange={(e) => setRiotId(e.target.value)}
            aria-label={t('riotIdAria')}
            disabled={collectDisabled}
          />
          <input
            type="number"
            min={1}
            max={20}
            className={`${inputCls} w-16`}
            value={count}
            onChange={(e) => setCount(Math.max(1, Math.min(20, Number(e.target.value) || 1)))}
            aria-label={t('countAria')}
            disabled={collectDisabled}
          />
          <button type="submit" className={btnCls} disabled={collectDisabled || !riotId.includes('#')}>
            {busy === 'player' ? t('collecting') : t('collectPlayer')}
          </button>
        </form>
      </div>

      {(message || results.length > 0) && (
        <div className="mx-auto max-w-[1600px] px-4 pb-3 text-sm" role="status" aria-live="polite">
          {message && <p className={message.tone === 'error' ? 'text-rose-300' : 'text-emerald-300'}>{message.text}</p>}
          {results.length > 0 && (
            <ul className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs">
              {results.map((r) => (
                <li key={r.match_id}>
                  <button
                    type="button"
                    className={`underline-offset-2 hover:underline ${stateClass[r.state]}`}
                    onClick={() => r.state !== 'error' && onSelect(r.match_id)}
                    disabled={r.state === 'error'}
                    title={r.detail}
                  >
                    {r.match_id} · {collectState(r.state)}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </header>
  );
}
