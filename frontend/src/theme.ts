// Shared palette and formatting helpers.
import type { Role, Severity, Team } from './types';

export const COLORS = {
  bg: '#0f172a',
  panel: '#1e293b',
  border: '#334155',
  text: '#e2e8f0',
  muted: '#94a3b8',
  blue: '#06b6d4',
  red: '#f43f5e',
  amber: '#f59e0b',
} as const;

export const teamColor = (t: Team) => (t === 'blue' ? COLORS.blue : COLORS.red);
export const teamLabel = (t: Team) => (t === 'blue' ? 'Blue' : 'Red');

export const ROLE_ORDER: Role[] = ['TOP', 'JUNGLE', 'MIDDLE', 'BOTTOM', 'UTILITY'];
export const ROLE_SHORT: Record<Role, string> = { TOP: 'TOP', JUNGLE: 'JGL', MIDDLE: 'MID', BOTTOM: 'BOT', UTILITY: 'SUP' };

export const SEVERITY_CLASS: Record<Severity, string> = {
  LOW: 'bg-amber-950 text-amber-200 border-amber-800',
  MEDIUM: 'bg-amber-900 text-amber-100 border-amber-600',
  HIGH: 'bg-amber-500 text-slate-950 border-amber-300',
};

export const pct = (p: number, digits = 0) => `${(p * 100).toFixed(digits)}%`;
export const signedPct = (p: number, digits = 1) => `${p >= 0 ? '+' : '−'}${Math.abs(p * 100).toFixed(digits)}%`;
export const fmtGold = (g: number) => (Math.abs(g) >= 1000 ? `${(g / 1000).toFixed(1)}k` : `${Math.round(g)}`);
export const signedGold = (g: number) => `${g >= 0 ? '+' : '−'}${fmtGold(Math.abs(g))}`;
export const humanize = (s: string) => s.toLowerCase().replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase());

export const escapeHtml = (s: string) =>
  s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c] as string);
