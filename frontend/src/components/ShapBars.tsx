import type { ShapFeature } from '../types';
import { signedPct } from '../theme';

interface Props {
  features: ShapFeature[];
  /** Optional compact mode used inside cards. */
  compact?: boolean;
}

/** Signed horizontal bars: right/cyan pushes toward Blue, left/rose toward Red. */
export function ShapBars({ features, compact = false }: Props) {
  if (features.length === 0) return <p className="text-sm text-slate-400">No feature attribution for this minute.</p>;
  const max = Math.max(...features.map((f) => Math.abs(f.contribution)), 0.01);
  return (
    <ul className="space-y-2" aria-label="Feature contributions to blue win probability">
      {features.map((f) => {
        const w = (Math.abs(f.contribution) / max) * 50;
        const pos = f.contribution >= 0;
        return (
          <li key={f.feature} className="text-sm">
            <div className="mb-0.5 flex justify-between gap-2">
              <span className="truncate text-slate-200">
                {f.label}
                {!compact && <span className="text-slate-400"> · value {Number.isInteger(f.value) ? f.value : f.value.toFixed(2)}</span>}
              </span>
              <span className={`tabular-nums font-semibold ${pos ? 'text-side-blue' : 'text-side-red'}`}>
                {signedPct(f.contribution)} {pos ? 'Blue' : 'Red'}
              </span>
            </div>
            <div className="relative h-2.5 rounded bg-slate-700" role="img" aria-label={`${f.label}: ${signedPct(f.contribution)} toward ${pos ? 'blue' : 'red'}`}>
              <span className="absolute inset-y-0 left-1/2 w-px bg-slate-400" aria-hidden="true" />
              <span
                className={`absolute inset-y-0 rounded ${pos ? 'bg-side-blue' : 'bg-side-red'}`}
                style={pos ? { left: '50%', width: `${w}%` } : { right: '50%', width: `${w}%` }}
                aria-hidden="true"
              />
            </div>
          </li>
        );
      })}
    </ul>
  );
}
