"use client";

import { useEffect, useMemo, useState } from "react";
import { api, fmt$, type Roster, type Team, type TradeResponse } from "@/lib/api";
import { useAiVetoDisabled } from "@/lib/ai-veto";
import { BackButton } from "@/app/back-button";

type PickRow = { id: number; year: number; round: number; original: string };

export default function TradePage() {
  const [teams, setTeams] = useState<Team[]>([]);
  // Team A defaults to user's chosen team (read from localStorage on mount)
  const [teamA, setTeamA] = useState("LAL");
  const [teamB, setTeamB] = useState("MIA");
  const [teamC, setTeamC] = useState<string | null>(null);
  const [rosters, setRosters] = useState<Record<string, Roster | null>>({});
  const [picks, setPicks] = useState<Record<string, PickRow[]>>({});
  const [selPlayers, setSelPlayers] = useState<Record<string, Set<number>>>({});
  const [selPicks, setSelPicks] = useState<Record<string, Set<number>>>({});
  const [destPlayer, setDestPlayer] = useState<Record<number, string>>({});
  const [destPick, setDestPick] = useState<Record<number, string>>({});
  const [careerMode, setCareerMode] = useState(false);
  const [userTeam, setUserTeam] = useState("LAL");
  const [season, setSeason] = useState("2026-27");
  const [aiDisabled, setAiDisabled] = useAiVetoDisabled();
  const [result, setResult] = useState<TradeResponse | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const activeTeams = useMemo(
    () => [teamA, teamB, ...(teamC ? [teamC] : [])],
    [teamA, teamB, teamC]
  );

  useEffect(() => {
    api.teams().then(setTeams).catch((e) => setError(String(e)));
    api.state().then(s => setSeason(s.current_season)).catch(() => {});
    if (typeof window !== "undefined") {
      const saved = localStorage.getItem("nba_gm_user_team");
      if (saved) {
        setUserTeam(saved);
        setTeamA(saved);   // auto-load user's team as Team A
        // Pick a different team for Team B if same
        if (saved === "MIA") setTeamB("LAL");
      }
      if (localStorage.getItem("nba_gm_mode") === "career") setCareerMode(true);
    }
  }, []);

  // Load roster + picks for each active team
  useEffect(() => {
    const load = async () => {
      const allYears = await Promise.all(
        [2026, 2027, 2028, 2029, 2030].map((y) => api.draftOrder(y).then((picks) => ({ year: y, picks })))
      );
      const newRosters: Record<string, Roster> = {};
      const newPicks: Record<string, PickRow[]> = {};
      await Promise.all(
        activeTeams.map(async (t) => {
          const r = await api.roster(t);
          newRosters[t] = r;
          const owned: PickRow[] = [];
          for (const { year, picks } of allYears) {
            for (const p of picks) {
              if (p.owner === t) owned.push({ id: p.id, year, round: p.round, original: p.original });
            }
          }
          newPicks[t] = owned;
        })
      );
      setRosters(newRosters);
      setPicks(newPicks);
    };
    load();
    // Reset selections for teams that are no longer active
    setSelPlayers((prev) => {
      const next: Record<string, Set<number>> = {};
      for (const t of activeTeams) next[t] = prev[t] ?? new Set();
      return next;
    });
    setSelPicks((prev) => {
      const next: Record<string, Set<number>> = {};
      for (const t of activeTeams) next[t] = prev[t] ?? new Set();
      return next;
    });
  }, [teamA, teamB, teamC]);

  const defaultDest = (srcTeam: string): string => {
    const others = activeTeams.filter((t) => t !== srcTeam);
    return others[0] ?? srcTeam;
  };

  const toggle = (kind: "player" | "pick", team: string, id: number) => {
    const setter = kind === "player" ? setSelPlayers : setSelPicks;
    setter((prev) => {
      const next = { ...prev };
      const cur = new Set(next[team] ?? []);
      if (cur.has(id)) cur.delete(id);
      else {
        cur.add(id);
        if (activeTeams.length > 2) {
          const destSetter = kind === "player" ? setDestPlayer : setDestPick;
          destSetter((d) => ({ ...d, [id]: d[id] ?? defaultDest(team) }));
        }
      }
      next[team] = cur;
      return next;
    });
  };

  const setDestForAsset = (kind: "player" | "pick", id: number, dest: string) => {
    (kind === "player" ? setDestPlayer : setDestPick)((d) => ({ ...d, [id]: dest }));
  };

  // Outgoing salary per team (for net swing display)
  const outSalary = (team: string): number => {
    const r = rosters[team];
    const sel = selPlayers[team] ?? new Set();
    if (!r) return 0;
    return r.players
      .filter((p) => sel.has(p.id))
      .reduce((sum, p) => sum + (p.contract?.seasons.find((s) => s.season === season)?.salary ?? 0), 0);
  };

  const buildDestinations = (): Record<string, string> => {
    if (activeTeams.length < 3) return {};
    const dests: Record<string, string> = {};
    for (const team of activeTeams) {
      for (const id of selPlayers[team] ?? []) {
        dests[`player:${id}`] = destPlayer[id] ?? defaultDest(team);
      }
      for (const id of selPicks[team] ?? []) {
        dests[`pick:${id}`] = destPick[id] ?? defaultDest(team);
      }
    }
    return dests;
  };

  const submit = async (apply: boolean) => {
    setError(null);
    setResult(null);
    setSubmitting(true);
    try {
      const r = await api.proposeTrade({
        season,
        apply,
        career_mode: careerMode && !aiDisabled,   // turning off AI bypasses career checks
        user_team: userTeam,
        destinations: buildDestinations(),
        legs: activeTeams.map((t) => ({
          team: t,
          outgoing_player_ids: [...(selPlayers[t] ?? [])],
          outgoing_pick_ids: [...(selPicks[t] ?? [])],
        })),
      });
      setResult(r);
    } catch (e) {
      setError(String(e));
    } finally {
      setSubmitting(false);
    }
  };

  const totalSelected = activeTeams.reduce(
    (n, t) => n + (selPlayers[t]?.size ?? 0) + (selPicks[t]?.size ?? 0),
    0
  );

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      <BackButton />
      <div className="flex items-start justify-between mb-6 gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight mb-2">Trade Machine</h1>
          <p className="text-zinc-400 text-sm">
            CBA-enforced. Salary matching (4 tiers), apron restrictions, Stepien rule. Supports 2 or 3 teams.
          </p>
        </div>
        <div className="flex items-center gap-3 text-sm bg-zinc-900 border border-zinc-800 rounded-lg px-4 py-2">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={careerMode}
              onChange={(e) => {
                setCareerMode(e.target.checked);
                if (typeof window !== "undefined") localStorage.setItem("nba_gm_career_mode", String(e.target.checked));
              }}
              className="accent-orange-500"
            />
            <span>Career Mode</span>
          </label>
          {careerMode && (
            <div className="flex items-center gap-1 border-l border-zinc-700 pl-3">
              <span className="text-zinc-500 text-xs">You:</span>
              <input
                value={userTeam}
                onChange={(e) => {
                  const v = e.target.value.toUpperCase();
                  setUserTeam(v);
                  if (typeof window !== "undefined") localStorage.setItem("nba_gm_user_team", v);
                }}
                className="bg-zinc-800 border border-zinc-700 rounded px-2 py-0.5 text-sm w-16 font-mono"
              />
            </div>
          )}
        </div>
      </div>

      <div className={`grid gap-4 mb-4 ${teamC ? "grid-cols-1 md:grid-cols-3" : "grid-cols-1 md:grid-cols-2"}`}>
        {activeTeams.map((t, i) => (
          <TradeSide
            key={t + i}
            label={`Team ${String.fromCharCode(65 + i)}`}
            team={t}
            setTeam={(v) => {
              if (i === 0) setTeamA(v);
              else if (i === 1) setTeamB(v);
              else setTeamC(v);
            }}
            teams={teams}
            activeTeams={activeTeams}
            roster={rosters[t] ?? null}
            picks={picks[t] ?? []}
            selPlayers={selPlayers[t] ?? new Set()}
            selPicks={selPicks[t] ?? new Set()}
            destPlayer={destPlayer}
            destPick={destPick}
            onTogglePlayer={(id) => toggle("player", t, id)}
            onTogglePick={(id) => toggle("pick", t, id)}
            onChangeDest={(kind, id, dest) => setDestForAsset(kind, id, dest)}
            outSalary={outSalary(t)}
          />
        ))}
      </div>

      <div className="flex items-center justify-between bg-zinc-900 border border-zinc-800 rounded-lg p-4 mb-3">
        <div className="text-sm">
          {!teamC ? (
            <button
              onClick={() => setTeamC("HOU")}
              className="text-xs px-2.5 py-1 rounded border border-dashed border-zinc-700 hover:border-zinc-500 hover:bg-zinc-800/50 text-zinc-300"
            >
              + Add 3rd Team
            </button>
          ) : (
            <button
              onClick={() => {
                setTeamC(null);
                setDestPlayer({});
                setDestPick({});
              }}
              className="text-xs px-2.5 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-400"
            >
              − Remove 3rd Team
            </button>
          )}
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => submit(false)}
            disabled={submitting || totalSelected === 0}
            className="px-4 py-2 rounded-md bg-zinc-800 hover:bg-zinc-700 text-sm font-medium disabled:opacity-50"
          >
            Validate CBA{careerMode ? " + AI" : ""}
          </button>
          <button
            onClick={() => submit(true)}
            disabled={submitting || !result?.valid || (careerMode && !!result?.ai_evaluations?.some((e) => !e.accepts))}
            className="px-4 py-2 rounded-md bg-orange-500 hover:bg-orange-400 text-black text-sm font-semibold disabled:opacity-50"
          >
            Execute Trade
          </button>
        </div>
      </div>

      {error && <div className="mb-3 p-3 rounded border border-red-800 bg-red-900/20 text-red-300 text-sm">{error}</div>}

      {result && (
        <div className={`p-4 rounded-lg border ${result.applied ? "border-emerald-700 bg-emerald-900/20" : result.valid ? "border-emerald-800 bg-emerald-900/10" : "border-red-800 bg-red-900/10"}`}>
          <div className={`font-semibold ${result.applied ? "text-emerald-300" : result.valid ? "text-emerald-400" : "text-red-400"}`}>
            {result.applied ? "✓ Trade executed!" : result.valid ? "✓ Trade is LEGAL under the CBA" : "✗ Trade is ILLEGAL"}
          </div>
          {result.violations.length > 0 && (
            <ul className="mt-3 space-y-1 text-sm">
              {result.violations.map((v, i) => (
                <li key={i} className={v.severity === "BLOCKER" ? "text-red-300" : "text-yellow-300"}>
                  <span className="font-mono text-xs mr-2">[{v.severity}]</span>
                  {v.message}
                </li>
              ))}
            </ul>
          )}
          {result.ai_evaluations && result.ai_evaluations.length > 0 && (
            <div className="mt-4 pt-3 border-t border-zinc-800">
              <div className="text-xs uppercase tracking-wider text-zinc-500 mb-2">AI Trade Evaluation</div>
              {result.ai_evaluations.map((e, i) => (
                <div key={i} className={`text-sm py-1 ${e.accepts ? "text-emerald-300" : "text-red-300"}`}>
                  <span className="font-bold mr-2">{e.accepts ? "✓ ACCEPT" : "✗ REJECT"}</span>
                  <span className="font-mono mr-2">{e.team}:</span>
                  {e.explanation}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function TradeSide({
  label, team, setTeam, teams, activeTeams, roster, picks,
  selPlayers, selPicks, destPlayer, destPick,
  onTogglePlayer, onTogglePick, onChangeDest, outSalary,
}: {
  label: string;
  team: string;
  setTeam: (t: string) => void;
  teams: Team[];
  activeTeams: string[];
  roster: Roster | null;
  picks: PickRow[];
  selPlayers: Set<number>;
  selPicks: Set<number>;
  destPlayer: Record<number, string>;
  destPick: Record<number, string>;
  onTogglePlayer: (id: number) => void;
  onTogglePick: (id: number) => void;
  onChangeDest: (kind: "player" | "pick", id: number, dest: string) => void;
  outSalary: number;
}) {
  const showDest = activeTeams.length > 2;
  const otherTeams = activeTeams.filter((t) => t !== team);
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <div>
          <div className="text-xs uppercase tracking-wider text-zinc-500">{label}</div>
          <div className="mt-1 flex items-center gap-2">
            {teams.find(t => t.tricode === team)?.logo_url && (
              <img src={teams.find(t => t.tricode === team)?.logo_url} alt="" className="w-7 h-7 object-contain" />
            )}
            <select
              value={team}
              onChange={(e) => setTeam(e.target.value)}
              className="bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-sm"
            >
              <optgroup label="Eastern Conference">
                {teams.filter(t => t.conference === "East").map((t) => (
                  <option key={t.tricode} value={t.tricode}>{t.full_name}</option>
                ))}
              </optgroup>
              <optgroup label="Western Conference">
                {teams.filter(t => t.conference === "West").map((t) => (
                  <option key={t.tricode} value={t.tricode}>{t.full_name}</option>
                ))}
              </optgroup>
            </select>
          </div>
        </div>
        <div className="text-right text-sm">
          <div className="text-zinc-500 text-xs">Outgoing</div>
          <div className="font-semibold">{fmt$(outSalary)}</div>
        </div>
      </div>

      <div className="text-xs uppercase tracking-wider text-zinc-500 mb-1">Players</div>
      <div className="space-y-1 max-h-72 overflow-y-auto mb-3">
        {roster?.players
          .filter((p) => p.contract?.seasons.find((s) => true))
          .sort((a, b) => {
            const sa = a.contract?.seasons[0]?.salary ?? 0;
            const sb = b.contract?.seasons[0]?.salary ?? 0;
            return sb - sa;
          })
          .map((p) => {
            const sal = p.contract?.seasons[0]?.salary ?? 0;
            const checked = selPlayers.has(p.id);
            return (
              <div
                key={p.id}
                className={`flex items-center justify-between gap-2 px-2 py-1.5 rounded text-sm hover:bg-zinc-800/50 ${checked ? "bg-orange-900/20 ring-1 ring-orange-500/40" : ""}`}
              >
                <label className="flex items-center gap-2 cursor-pointer flex-1">
                  <input type="checkbox" checked={checked} onChange={() => onTogglePlayer(p.id)} className="accent-orange-500" />
                  <span>{p.name}</span>
                  {p.overall != null && <span className="text-xs text-zinc-500">({p.overall})</span>}
                </label>
                <span className="font-mono text-xs text-zinc-400">{fmt$(sal)}</span>
                {showDest && checked && (
                  <select
                    value={destPlayer[p.id] ?? otherTeams[0]}
                    onChange={(e) => onChangeDest("player", p.id, e.target.value)}
                    className="bg-zinc-800 border border-zinc-700 rounded text-xs px-1 py-0.5"
                  >
                    {otherTeams.map((t) => (
                      <option key={t} value={t}>→ {t}</option>
                    ))}
                  </select>
                )}
              </div>
            );
          })}
      </div>

      <div className="text-xs uppercase tracking-wider text-zinc-500 mb-1">Picks</div>
      <div className="space-y-1 max-h-40 overflow-y-auto">
        {picks.length === 0 && <div className="text-xs text-zinc-600 italic">No picks loaded</div>}
        {picks.sort((a, b) => a.year - b.year || a.round - b.round).map((p) => {
          const checked = selPicks.has(p.id);
          return (
            <div
              key={p.id}
              className={`flex items-center justify-between gap-2 px-2 py-1 rounded text-sm hover:bg-zinc-800/50 ${checked ? "bg-orange-900/20 ring-1 ring-orange-500/40" : ""}`}
            >
              <label className="flex items-center gap-2 cursor-pointer flex-1">
                <input type="checkbox" checked={checked} onChange={() => onTogglePick(p.id)} className="accent-orange-500" />
                <span>{p.year} R{p.round} {p.original !== team && <span className="text-zinc-500">(from {p.original})</span>}</span>
              </label>
              {showDest && checked && (
                <select
                  value={destPick[p.id] ?? otherTeams[0]}
                  onChange={(e) => onChangeDest("pick", p.id, e.target.value)}
                  className="bg-zinc-800 border border-zinc-700 rounded text-xs px-1 py-0.5"
                >
                  {otherTeams.map((t) => (
                    <option key={t} value={t}>→ {t}</option>
                  ))}
                </select>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
