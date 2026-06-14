"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, fmt$, type Roster, type Team, type TradeResponse } from "@/lib/api";
import { useAiVetoDisabled } from "@/lib/ai-veto";
import { useUserContext } from "@/lib/user-context";
import { BackButton } from "@/app/back-button";
import { TeamExceptionsPanel } from "@/app/team-exceptions-panel";

type PickRow = { id: number; year: number; round: number; original: string };

const MAX_TEAMS = 4;
const FILLER_TEAMS = ["LAL", "MIA", "HOU", "BOS"];

export default function TradePage() {
  const router = useRouter();
  const { team: ctxUserTeam, mode } = useUserContext();
  const [teams, setTeams] = useState<Team[]>([]);
  const [tricodes, setTricodes] = useState<string[]>(["LAL", "MIA"]);
  const [rosters, setRosters] = useState<Record<string, Roster | null>>({});
  const [picks, setPicks] = useState<Record<string, PickRow[]>>({});
  const [selPlayers, setSelPlayers] = useState<Record<string, Set<number>>>({});
  const [selPicks, setSelPicks] = useState<Record<string, Set<number>>>({});
  const [destPlayer, setDestPlayer] = useState<Record<number, string>>({});
  const [destPick, setDestPick] = useState<Record<number, string>>({});
  const [season, setSeason] = useState("2026-27");
  const [aiDisabled, setAiDisabled] = useAiVetoDisabled();
  const userTeam = ctxUserTeam ?? "";
  const careerMode = mode === "career";
  const [result, setResult] = useState<TradeResponse | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const activeTeams = tricodes;

  const setTeamAt = (i: number, value: string) =>
    setTricodes(prev => prev.map((t, idx) => (idx === i ? value : t)));

  const addTeam = () => {
    if (tricodes.length >= MAX_TEAMS) return;
    const filler = FILLER_TEAMS.find(t => !tricodes.includes(t)) ?? "SAS";
    setTricodes(prev => [...prev, filler]);
  };

  const removeTeam = (i: number) => {
    if (tricodes.length <= 2) return;
    setTricodes(prev => prev.filter((_, idx) => idx !== i));
    setDestPlayer({});
    setDestPick({});
  };

  useEffect(() => {
    api.teams().then(setTeams).catch((e) => setError(String(e)));
    api.state().then(s => setSeason(s.current_season)).catch(() => {});
  }, []);

  // Sync Team A with the user's chosen team whenever the context loads.
  useEffect(() => {
    if (!ctxUserTeam) return;
    setTricodes(prev => {
      if (prev[0] === ctxUserTeam) return prev;
      const next = [...prev];
      next[0] = ctxUserTeam;
      // Make sure no other slot duplicates the user's team
      for (let i = 1; i < next.length; i++) {
        if (next[i] === ctxUserTeam) {
          next[i] = FILLER_TEAMS.find(t => !next.includes(t)) ?? "SAS";
        }
      }
      return next;
    });
  }, [ctxUserTeam]);

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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tricodes.join(",")]);

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
      if (r.applied) {
        // Refresh rosters in this view, and invalidate Next's route cache so the
        // team page reflects the new rosters when the user navigates back.
        await Promise.all(activeTeams.map(t => api.roster(t).then(rs => setRosters(prev => ({ ...prev, [t]: rs })))));
        setSelPlayers({}); setSelPicks({});
        router.refresh();
      }
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
          <h1 className="text-3xl font-bold tracking-tight">Trade Machine</h1>
          <p className="text-zinc-400 text-sm mt-1">
            CBA-enforced: salary matching, apron restrictions, Stepien rule. Supports 2 or 3 teams.
            {careerMode && userTeam && (
              <span className="ml-2 text-orange-400">· You GM {userTeam} — AI evaluates other teams&apos; legs.</span>
            )}
          </p>
        </div>
        {userTeam && (
          <Link href={`/team/${userTeam}`} className="shrink-0 px-4 py-2 rounded-md bg-orange-500 hover:bg-orange-400 text-black font-semibold text-sm whitespace-nowrap">
            Done — back to team →
          </Link>
        )}
      </div>

      {/* Team count controls */}
      <div className="flex items-center gap-2 mb-3 text-xs">
        <span className="text-zinc-500">{tricodes.length} team{tricodes.length === 1 ? "" : "s"} in this trade</span>
        {tricodes.length < MAX_TEAMS && (
          <button
            onClick={addTeam}
            className="px-2.5 py-1 rounded border border-dashed border-emerald-700/60 hover:border-emerald-500 hover:bg-emerald-900/20 text-emerald-300"
          >
            + Add team {tricodes.length === 2 ? "(3-team trade)" : tricodes.length === 3 ? "(4-team trade)" : ""}
          </button>
        )}
      </div>

      <div className={`grid gap-4 mb-4 ${
        tricodes.length === 4 ? "grid-cols-1 md:grid-cols-2 xl:grid-cols-4" :
        tricodes.length === 3 ? "grid-cols-1 md:grid-cols-3" :
        "grid-cols-1 md:grid-cols-2"
      }`}>
        {activeTeams.map((t, i) => (
          <TradeSide
            key={t + i}
            label={`Team ${String.fromCharCode(65 + i)}`}
            team={t}
            setTeam={(v) => setTeamAt(i, v)}
            canRemove={tricodes.length > 2}
            onRemove={() => removeTeam(i)}
            teams={teams}
            activeTeams={activeTeams}
            roster={rosters[t] ?? null}
            picks={picks[t] ?? []}
            season={season}
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

      <div className="flex items-center justify-end bg-zinc-900 border border-zinc-800 rounded-lg p-4 mb-3">
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
  label, team, setTeam, canRemove, onRemove, teams, activeTeams, roster, picks, season,
  selPlayers, selPicks, destPlayer, destPick,
  onTogglePlayer, onTogglePick, onChangeDest, outSalary,
}: {
  label: string;
  team: string;
  setTeam: (t: string) => void;
  canRemove: boolean;
  onRemove: () => void;
  teams: Team[];
  activeTeams: string[];
  roster: Roster | null;
  picks: PickRow[];
  season: string;
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
          <div className="flex items-center gap-2">
            <div className="text-xs uppercase tracking-wider text-zinc-500">{label}</div>
            {canRemove && (
              <button
                onClick={onRemove}
                title="Remove this team from the trade"
                className="text-[10px] px-1.5 py-0.5 rounded border border-zinc-700 hover:border-red-700 hover:bg-red-900/30 text-zinc-500 hover:text-red-300"
              >
                Remove
              </button>
            )}
          </div>
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

      <div className="mb-3">
        <TeamExceptionsPanel tricode={team} season={season} variant="tpe-only" />
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
