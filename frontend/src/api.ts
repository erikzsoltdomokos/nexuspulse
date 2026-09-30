// Thin typed client for the NexusPulse backend. All paths are relative to /api,
// which the Vite dev server proxies to the Python backend.
import type {
  CollectPlayerResult,
  CollectResult,
  Health,
  MatchList,
  Overview,
  TimelineDynamics,
} from './types';

const BASE = '/api';
const DEFAULT_TIMEOUT_MS = 15_000;

export class ApiError extends Error {
  /** HTTP status, or 0 when the backend could not be reached at all. */
  readonly status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
  get unreachable(): boolean {
    // 0 = network failure; 502/503/504 = Vite proxy could not reach the backend.
    return this.status === 0 || this.status === 502 || this.status === 503 || this.status === 504;
  }
}

async function request<T>(path: string, init: RequestInit = {}, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      ...init,
      signal: controller.signal,
      headers: { Accept: 'application/json', ...(init.body ? { 'Content-Type': 'application/json' } : {}), ...init.headers },
    });
  } catch (err) {
    const aborted = err instanceof DOMException && err.name === 'AbortError';
    throw new ApiError(aborted ? 'Request timed out' : 'Backend unreachable', 0);
  } finally {
    window.clearTimeout(timer);
  }
  if (!res.ok) {
    let detail = res.statusText || `HTTP ${res.status}`;
    try {
      const body: unknown = await res.json();
      if (body && typeof body === 'object' && 'detail' in body) {
        const d = (body as { detail: unknown }).detail;
        detail = typeof d === 'string' ? d : JSON.stringify(d);
      }
    } catch {
      // Non-JSON error body; keep the status text.
    }
    throw new ApiError(detail, res.status);
  }
  try {
    return (await res.json()) as T;
  } catch {
    throw new ApiError('Invalid JSON from backend', res.status);
  }
}

export const api = {
  health: () => request<Health>('/health', {}, 5_000),
  matches: () => request<MatchList>('/matches'),
  collectMatch: (match_id: string) =>
    request<CollectResult>('/collect-match', { method: 'POST', body: JSON.stringify({ match_id }) }, 120_000),
  collectPlayer: (game_name: string, tag_line: string, count: number) =>
    request<CollectPlayerResult>(
      '/collect-player',
      { method: 'POST', body: JSON.stringify({ game_name, tag_line, count }) },
      300_000,
    ),
  overview: (id: string) => request<Overview>(`/analysis/${encodeURIComponent(id)}/overview`),
  dynamics: (id: string) => request<TimelineDynamics>(`/analysis/${encodeURIComponent(id)}/timeline-dynamics`, {}, 60_000),
};

/** Lazily loads the bundled demo match so it does not bloat the main chunk. */
export async function loadDemo(): Promise<{ overview: Overview; dynamics: TimelineDynamics }> {
  const [o, d] = await Promise.all([import('./mock/sampleOverview.json'), import('./mock/sampleDynamics.json')]);
  return { overview: o.default as Overview, dynamics: d.default as TimelineDynamics };
}
