import type { InflectionPoint, TimelinePoint } from '../types';
import { pct, signedPct, teamLabel } from '../theme';
import { ShapBars } from './ShapBars';

interface Props {
  inflections: InflectionPoint[];
  timeline: TimelinePoint[];
  activeMinute: number | null;
  onSelect: (minute: number) => void;
  onClear: () => void;
}

export function InflectionPanel({ inflections, timeline, activeMinute, onSelect, onClear }: Props) {
  const active = inflections.find((i) => i.minute === activeMinute) ?? null;
  const point = active ? timeline.find((t) => t.minute === active.minute) : undefined;
  const features = active ? (active.top_features.length ? active.top_features : point?.shap_summary ?? []) : [];

  return (
    <section aria-labelledby="inflections-title" className="flex flex-col gap-3 rounded-lg border border-slate-800 bg-slate-900 p-3 text-slate-100">
      <h2 id="inflections-title" className="text-base font-semibold">
        Inflection points <span className="text-sm font-normal text-slate-400">({inflections.length})</span>
      </h2>
      {inflections.length === 0 ? (
        <p className="text-sm text-slate-400">No decisive swings detected in this match.</p>
      ) : (
        <ul className="grid max-h-72 gap-2 overflow-y-auto pr-1" aria-label="Inflection points, select to zoom the timeline">
          {inflections.map((ip) => {
            const selected = ip.minute === activeMinute;
            const toBlue = ip.direction === 'blue';
            return (
              <li key={ip.minute}>
                <button
                  type="button"
                  aria-pressed={selected}
                  onClick={() => onSelect(ip.minute)}
                  className={`w-full rounded-md border-l-4 px-3 py-2 text-left transition-colors ${toBlue ? 'border-side-blue' : 'border-side-red'} ${
                    selected ? 'bg-slate-700 ring-1 ring-inflect' : 'bg-slate-800 hover:bg-slate-700'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2 text-sm">
                    <span className="font-semibold text-inflect">◆ {ip.minute}:00</span>
                    <span className={`tabular-nums font-semibold ${toBlue ? 'text-side-blue' : 'text-side-red'}`}>
                      {signedPct(ip.delta)} → {teamLabel(ip.direction)}
                    </span>
                  </div>
                  <p className="mt-0.5 text-xs text-slate-300">{ip.description}</p>
                </button>
              </li>
            );
          })}
        </ul>
      )}

      <div className="rounded-md border border-slate-700 bg-slate-950 p-3" aria-live="polite" aria-labelledby="shap-title">
        <div className="mb-2 flex items-center justify-between">
          <h3 id="shap-title" className="text-sm font-semibold">
            SHAP decomposition{active ? ` · minute ${active.minute}` : ''}
          </h3>
          {active && (
            <button type="button" onClick={onClear} className="rounded bg-slate-700 px-2 py-0.5 text-xs text-slate-100 hover:bg-slate-600">
              Close
            </button>
          )}
        </div>
        {active ? (
          <>
            {point && (
              <p className="mb-2 text-xs text-slate-400">
                Blue win probability {pct(point.win_probability_blue - point.delta_win_probability)} → {pct(point.win_probability_blue)}
              </p>
            )}
            <ShapBars features={features} />
            <p className="mt-2 text-xs text-slate-500">Bars show signed change in blue win probability: cyan favours Blue, rose favours Red.</p>
          </>
        ) : (
          <p className="text-sm text-slate-400">Select an inflection card (or a pin on the chart) to see what drove the swing.</p>
        )}
      </div>
    </section>
  );
}
