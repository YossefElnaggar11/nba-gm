const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8765";

export type Team = {
  tricode: string;
  full_name: string;
  conference: "East" | "West";
  division: string;
  primary_color: string;
  secondary_color: string;
  logo_url: string;
};

export type ContractSeason = {
  season: string;
  salary: number;
  option_type: "NONE" | "PLAYER" | "TEAM" | "EARLY_TERMINATION";
  guaranteed: boolean;
};

export type Contract = {
  id: number;
  signed_using: string | null;
  seasons: ContractSeason[];
};

export type Player = {
  id: number;
  name: string;
  age: number | null;
  position: string | null;
  overall: number | null;
  potential: number | null;
  years_of_service: number;
  contract: Contract | null;
  last_season_stats?: {
    ppg: number;
    rpg: number;
    apg: number;
    spg: number;
    bpg: number;
    mpg: number;
  } | null;
};

export type OwnFA = {
  hold_id: number;
  player_id: number;
  name: string;
  age: number | null;
  position: string | null;
  overall: number | null;
  years_of_service: number;
  fa_type: "UFA" | "RFA" | "PO" | "TO" | "TWO_WAY";
  hold_amount: number;
  market_value: number;
  min_salary: number;
  bird_eligible: boolean;
};

export type Roster = { team: string; players: Player[]; count: number };

export type CapSheet = {
  team: string;
  season: string;
  cap_levels: {
    salary_cap: number;
    luxury_tax: number;
    first_apron: number;
    second_apron: number;
  };
  salary_total: number;
  cap_holds_total: number;
  total_salary: number;
  cap_space: number;
  over_tax: boolean;
  over_first_apron: boolean;
  over_second_apron: boolean;
  players: {
    player_id: number;
    name: string;
    age: number | null;
    overall: number | null;
    position: string | null;
    salary: number;
    option_type: string;
    guaranteed: boolean;
    is_two_way: boolean;
  }[];
  cap_holds: {
    hold_id: number;
    player_id: number;
    name: string;
    age: number | null;
    amount: number;
    notes: string | null;
  }[];
};

export type ExceptionInfo = {
  label: string;
  amount: number;
  available: boolean;
  note: string;
};

export type TeamExceptions = {
  team: string;
  season: string;
  is_over_cap: boolean;
  is_above_tax: boolean;
  is_above_first_apron: boolean;
  is_above_second_apron: boolean;
  cap_space: number;
  mle: ExceptionInfo;
  bae: ExceptionInfo;
  minimum: ExceptionInfo;
  bird_eligible: {
    player_id: number;
    name: string;
    age: number | null;
    overall: number | null;
    position: string | null;
    hold_amount: number;
  }[];
  trade_exceptions: {
    id: number;
    amount_total: number;
    remaining: number;
    expires: string;
    source: string | null;
  }[];
};

export type DraftPick = {
  id: number;
  pick_number: number | null;
  round: number;
  owner: string;
  original: string;
  status: string;
  is_swap: boolean;
  protection: string | null;
  notes: string | null;
};

export type FreeAgent = {
  id: number;
  name: string;
  age: number | null;
  position: string | null;
  overall: number | null;
  potential?: number | null;
  years_of_service: number;
  fa_type: "UFA" | "RFA" | "PO" | "TO" | "TWO_WAY" | null;
  prior_team: string | null;
  market_value: number;
  min_salary_for_yos: number;
};

export type Violation = {
  code: string;
  severity: "BLOCKER" | "WARNING";
  message: string;
  team: string | null;
};

export type TradeProposal = {
  season?: string;
  apply?: boolean;
  career_mode?: boolean;
  user_team?: string;
  destinations?: Record<string, string>;
  legs: {
    team: string;
    outgoing_player_ids: number[];
    outgoing_pick_ids: number[];
    outgoing_cash?: number;
  }[];
};

export type AiEvaluation = {
  team: string;
  accepts: boolean;
  incoming_value: number;
  outgoing_value: number;
  explanation: string;
};

export type TradeResponse = {
  valid: boolean;
  violations: Violation[];
  applied: boolean;
  transaction_id: number | null;
  ai_evaluations: AiEvaluation[] | null;
  summary: {
    legs: {
      team: string;
      outgoing_players: { id: number; name: string; salary: number }[];
      outgoing_picks: { id: number; year: number; round: number; original: string; is_swap: boolean; protection: string | null }[];
      outgoing_salary: number;
      cap_before: number;
      tax_before: boolean;
      first_apron_before: boolean;
    }[];
    season: string;
  };
};

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    const message = typeof detail === "object" && detail && "message" in detail
      ? String((detail as { message: unknown }).message)
      : typeof detail === "string"
      ? detail
      : `Request failed (${status})`;
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

// Retry up to N times on network-level failures (e.g. backend restarting,
// transient connection refused). Doesn't retry on 4xx/5xx responses — only
// on actual fetch() rejections.
async function fetchWithRetry(url: string, init?: RequestInit, retries = 2): Promise<Response> {
  let lastErr: unknown;
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      return await fetch(url, init);
    } catch (e) {
      lastErr = e;
      if (attempt < retries) {
        // Tiny backoff: 150ms, 400ms
        await new Promise(r => setTimeout(r, attempt === 0 ? 150 : 400));
      }
    }
  }
  throw lastErr instanceof Error
    ? new Error(`Network error: ${lastErr.message} (after ${retries + 1} attempts)`)
    : new Error(`Network error after ${retries + 1} attempts`);
}

async function getJSON<T>(path: string): Promise<T> {
  const r = await fetchWithRetry(`${API_BASE}${path}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} on ${path}`);
  return r.json();
}

async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const r = await fetchWithRetry(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    // FastAPI wraps HTTPException body in {detail: ...}
    const detail = (data as { detail?: unknown }).detail ?? data;
    throw new ApiError(r.status, detail);
  }
  return data as T;
}

export type PendingOption = {
  contract_season_id: number;
  player_id: number;
  player_name: string;
  team: string;
  season: string;
  salary: number;
  option_type: string;
  decided_by: "PLAYER" | "TEAM";
};

export type SigningProposalIn = {
  player_id: number;
  team: string;
  first_season?: string;
  salary_year1: number;
  years?: number;
  raise_pct?: number;
  using?: string;
  no_trade_clause?: boolean;
  apply?: boolean;
  career_mode?: boolean;
};

export type SigningResponse = {
  valid: boolean;
  violations: Array<{ code: string; severity: string; message: string; team: string | null }>;
  applied: boolean;
  contract_id: number | null;
  player_accepts: boolean;
  market_value: number | null;
  explanation: string | null;
};

export type Prospect = {
  id: number;
  rank: number;
  name: string;
  position: string | null;
  college: string | null;
  age: number | null;
  overall: number | null;
  potential: number | null;
  drafted_to: string | null;
  drafted_at_pick: number | null;
};

export type NextPick = {
  done: boolean;
  pick_id?: number;
  pick_number?: number;
  round?: number;
  owner?: string;
  original?: string;
};

export type SimStanding = {
  tricode: string;
  wins: number;
  losses: number;
  conference: string;
  rating: number;
  playoff_exit: string | null;
};

export type AllNbaPick = { name: string; team: string; score: number; ppg: number; rpg: number; apg: number; ovr: number; conference: string };

export type SimResponse = {
  season: string;
  champion: string;
  finals_mvp: string;
  mvp: string | null;
  mvp_team: string | null;
  dpoy: string | null;
  dpoy_team: string | null;
  roy: string | null;
  roy_team: string | null;
  all_nba_first: AllNbaPick[];
  all_nba_second: AllNbaPick[];
  all_nba_third: AllNbaPick[];
  all_stars_east: AllNbaPick[];
  all_stars_west: AllNbaPick[];
  league_avg_rating: number;
  east_seeds: string[];
  west_seeds: string[];
  standings: SimStanding[];
};

export type StandingsResponse = {
  season: string;
  champion: string | null;
  teams: Array<{
    tricode: string;
    conference: string;
    wins: number;
    losses: number;
    seed: number | null;
    made_playoffs: boolean;
    playoff_exit_round: string | null;
  }>;
};

export const api = {
  teams: () => getJSON<Team[]>("/api/teams"),
  team: (t: string) => getJSON<Team>(`/api/teams/${t}`),
  roster: (t: string) => getJSON<Roster>(`/api/teams/${t}/roster`),
  ownFAs: (t: string) => getJSON<{ team: string; season: string; own_fas: OwnFA[] }>(`/api/teams/${t}/own-free-agents`),
  capSheet: (t: string, season = "2026-27") => getJSON<CapSheet>(`/api/cap/team/${t}?season=${season}`),
  teamExceptions: (t: string, season = "2026-27") => getJSON<TeamExceptions>(`/api/cap/team/${t}/exceptions?season=${season}`),
  capLevels: () => getJSON<Record<string, { salary_cap: number; luxury_tax: number; first_apron: number; second_apron: number; projected?: boolean }>>("/api/cap/levels"),
  draftOrder: (year: number) => getJSON<DraftPick[]>(`/api/draft/${year}/order`),
  teamArsenal: (t: string) => getJSON<{ team: string; picks: { year: number; round: number; pick_number: number | null; original: string; is_swap: boolean; protection: string | null }[] }>(`/api/draft/team/${t}/arsenal`),
  freeAgents: (faType?: string) => getJSON<FreeAgent[]>(`/api/free-agents${faType ? `?fa_type=${faType}` : ""}`),
  proposeTrade: (p: TradeProposal) => postJSON<TradeResponse>("/api/trades", p),
  pendingOptions: (team?: string, season = "2026-27") =>
    getJSON<PendingOption[]>(`/api/options/pending?season=${season}${team ? `&team=${team}` : ""}`),
  decideOption: (contract_season_id: number, pick_up: boolean, intent_to_resign = false) =>
    postJSON<{ ok: boolean; action: string; player: string; player_id: number; former_team: string; is_free_agent: boolean }>("/api/options/decide", { contract_season_id, pick_up, intent_to_resign }),
  undoOption: (contract_season_id: number) =>
    postJSON<{ ok: boolean; action?: string; player?: string; error?: string }>("/api/options/undo", { contract_season_id }),
  recentTransactions: (limit = 10, team?: string) =>
    getJSON<Array<{ id: number; occurred_at: string; type: string; description: string; payload: Record<string, unknown> }>>(`/api/transactions?limit=${limit}${team ? `&team=${team}` : ""}`),
  signPlayer: (s: SigningProposalIn) => postJSON<SigningResponse>("/api/signings", s),
  prospects: (year: number, availableOnly = true) =>
    getJSON<Prospect[]>(`/api/draft-picks/prospects/${year}?available_only=${availableOnly}`),
  simSeason: (season: string) => postJSON<SimResponse>(`/api/sim/season/${season}`, {}),
  standings: (season: string) => getJSON<StandingsResponse>(`/api/sim/standings/${season}`),
  teamStrength: (t: string, season = "2026-27") =>
    getJSON<{ team: string; season: string; rating: number; top8: { name: string; ovr: number }[] }>(`/api/sim/strength/${t}?season=${season}`),
  awardsHistory: () =>
    getJSON<Array<{ season: string; champion: string | null; finals_mvp: string | null; finals_mvp_team: string | null;
      mvp: string | null; mvp_team: string | null; dpoy: string | null; dpoy_team: string | null;
      roy: string | null; roy_team: string | null; }>>("/api/sim/awards-history"),
  leaders: (season: string) =>
    getJSON<{ season: string; ppg: { name: string; team: string; value: number; gp: number }[];
      rpg: { name: string; team: string; value: number; gp: number }[];
      apg: { name: string; team: string; value: number; gp: number }[];
      spg: { name: string; team: string; value: number; gp: number }[];
      bpg: { name: string; team: string; value: number; gp: number }[]; }>(`/api/leaders/${season}`),
  nextPick: (year: number) => getJSON<NextPick>(`/api/draft-picks/next-pick/${year}`),
  makePick: (pick_id: number, prospect_id: number) =>
    postJSON<{ ok: boolean; team: string; pick_number: number; round: number; player: { id: number; name: string; position: string | null; overall: number | null } }>("/api/draft-picks/pick", { pick_id, prospect_id }),
  autoPick: (year: number) =>
    postJSON<{ done?: boolean; team?: string; pick_number?: number; player?: { name: string; overall: number | null } }>(`/api/draft-picks/auto-pick?year=${year}`, {}),
  autoSimUntil: (year: number, until_team: string) =>
    postJSON<{ picks_made: number; next: NextPick }>(`/api/draft-picks/auto-sim-until?year=${year}&until_team=${until_team}`, {}),
  rollover: (from_season: string, to_season: string) =>
    postJSON<{ ok: boolean; contracts_dropped: number; new_free_agents: number; players_aged: number }>("/api/rollover", { from_season, to_season }),
  state: () => getJSON<{ current_season: string; current_draft_year: number; simmed_seasons: string[]; scope_done: boolean }>("/api/state"),
  reset: () => postJSON<{ ok: boolean; message: string }>("/api/admin/reset", {}),
  enterMode: (mode: "career" | "offseason") =>
    postJSON<{ ok: boolean; mode: string; message: string }>("/api/admin/enter-mode", { mode }),
  getMode: () => getJSON<{ mode: string }>("/api/admin/mode"),
  saveCareer: () => postJSON<{ ok: boolean; message: string }>("/api/admin/save-career", {}),
  releasePlayer: (player_id: number) =>
    postJSON<{ ok: boolean; player: string; released_from: string }>("/api/admin/release-player", { player_id }),
  renounceHold: (hold_id: number) =>
    postJSON<{ ok: boolean; player: string | null; amount_cleared: number }>(`/api/admin/renounce-hold/${hold_id}`, {}),
};

export const fmt$ = (n: number) =>
  n >= 1_000_000 ? `$${(n / 1_000_000).toFixed(1)}M` : `$${n.toLocaleString()}`;

export const fmt$Full = (n: number) => `$${n.toLocaleString()}`;
