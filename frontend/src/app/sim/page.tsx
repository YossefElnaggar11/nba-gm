"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, ApiError, type SimResponse } from "@/lib/api";
import { useUserContext } from "@/lib/user-context";
import { RosterPreview } from "@/app/team/[tricode]/roster-preview";
import { BackButton } from "@/app/back-button";

const EXIT_LABEL: Record<string, string> = {
  R1: "Lost R1",
  R2: "Lost R2",
  CONF_FINALS: "Lost CF",
  FINALS: "Lost Finals",
  CHAMPION: "🏆 CHAMPION",
};

type DraftStatus = { done: boolean; pending: number };

export default function SimPage() {
  const { team: userTeamCtx, mode } = useUserContext();
  const [season, setSeason] = useState("2026-27");
  const [draftYear, setDraftYear] = useState(2026);
  const [userTeam, setUserTeam] = useState("LAL");
  const [result, setResult] = useState<SimResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [simError, setSimError] = useState<string | null>(null);
  const [draftStatus, setDraftStatus] = useState<DraftStatus | null>(null);
  const [standardCount, setStandardCount] = useState<number | null>(null);

  // Re-read game state + draft progress + roster size
  const refreshStatus = async () => {
    try {
      const s = await api.state();
      setSeason(s.current_season);
      setDraftYear(s.current_draft_year);
      const nextPick = await api.nextPick(s.current_draft_year);
      const undrafted = nextPick.done ? 0 : await countUndrafted(s.current_draft_year);
      setDraftStatus({ done: undrafted === 0, pending: undrafted });
      // Check user team's roster size
      if (userTeamCtx) {
        const roster = await api.capSheet(userTeamCtx, s.current_season).catch(() => null);
        if (roster) setStandardCount(roster.players.filter(p => !p.is_two_way).length);
      }
    } catch {}
  };

  useEffect(() => {
    if (userTeamCtx) setUserTeam(userTeamCtx);
    refreshStatus();
  }, [userTeamCtx]);

  if (mode === "offseason") {
    return (
      <div className="max-w-2xl mx-auto px-6 py-12 text-center">
        <h1 className="text-2xl font-bold mb-3">Season simulation isn&apos;t part of Offseason Mode</h1>
        <p className="text-zinc-400 mb-6">
          In Offseason Mode, your goal is to build the roster going into the 2026-27 season — no in-season simulation.
          Switch to <span className="text-orange-400 font-semibold">Full GM Mode</span> to sim the regular season + playoffs and progress year-to-year.
        </p>
        <Link href="/" className="inline-block px-4 py-2 rounded bg-orange-500 text-black font-semibold">Switch mode</Link>
      </div>
    );
  }

  const sim = async () => {
    setBusy(true);
    setSimError(null);
    try {
      const r = await api.simSeason(season);
      setResult(r);
    } catch (e: unknown) {
      if (e instanceof ApiError) {
        const d = e.detail as { message?: string; blocked_by?: string; undrafted_count?: number } | undefined;
        const msg = d?.message ?? e.message;
        setSimError(msg);
      } else {
        setSimError(e instanceof Error ? e.message : String(e));
      }
      // Refresh status so the gating UI updates
      refreshStatus();
    } finally {
      setBusy(false);
    }
  };

  const startOver = async () => {
    if (!confirm("Start over from the 2026 offseason? All progress will be wiped and you'll go back to your team's starting roster.")) return;
    setBusy(true);
    try {
      await api.reset();
      setResult(null);
      setSeason("2026-27");
      window.location.href = "/";
    } finally { setBusy(false); }
  };

  const resimulate = async () => {
    setBusy(true);
    setSimError(null);
    try {
      const r = await api.simSeason(season);
      setResult(r);
    } catch (e) {
      setSimError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const rollover = async () => {
    if (!result) return;
    const nextSeason = season === "2026-27" ? "2027-28" : "2028-29";
    setBusy(true);
    try {
      const r = await api.rollover(season, nextSeason);
      // Land on the user's team page — the natural "season start" landing
      const tricode = userTeam || "OKC";
      window.location.href = `/team/${tricode}?rollover=${nextSeason}&dropped=${r.contracts_dropped}&new_fas=${r.new_free_agents}`;
    } finally {
      setBusy(false);
    }
  };

  const east = result?.standings.filter(s => s.conference === "East") ?? [];
  const west = result?.standings.filter(s => s.conference === "West") ?? [];
  const userRecord = result?.standings.find(s => s.tricode === userTeam);

  const rosterOverflow = standardCount !== null && standardCount > 15;
  const canSim = draftStatus?.done === true && !rosterOverflow;

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      <BackButton />
      <div className="flex items-center justify-between mb-6 gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Sim {season}</h1>
          <p className="text-zinc-400 mt-1">
            Regular season + 16-team playoffs + awards. Re-running replaces prior results.
          </p>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <select value={season} onChange={e => setSeason(e.target.value)} className="bg-zinc-800 border border-zinc-700 rounded px-2 py-1">
            <option value="2026-27">2026-27</option>
            <option value="2027-28">2027-28</option>
          </select>
          <button
            onClick={sim}
            disabled={busy || !canSim}
            title={
              !draftStatus?.done ? `Complete the ${draftYear} draft first` :
              rosterOverflow ? `Release ${standardCount! - 15} player(s) first` : ""
            }
            className="px-4 py-2 rounded bg-orange-500 hover:bg-orange-400 text-black font-semibold disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {busy ? "Simulating…" : "Sim Season"}
          </button>
        </div>
      </div>

      {/* Pre-sim gate: draft must be done */}
      {!draftStatus?.done && draftStatus && (
        <div className="mb-6 p-5 rounded-xl border-2 border-orange-500/60 bg-orange-900/10">
          <div className="flex items-center justify-between">
            <div>
              <div className="font-semibold text-orange-300 text-lg">⛔ {draftYear} Draft not complete</div>
              <div className="text-sm text-zinc-300 mt-1">
                You need to make all draft picks before you can sim the season ({draftStatus.pending} picks remaining).
              </div>
            </div>
            <Link href={`/draft/${draftYear}/live`} className="px-4 py-2 rounded bg-orange-500 hover:bg-orange-400 text-black font-bold">
              → Go to Live Draft
            </Link>
          </div>
        </div>
      )}

      {/* Pre-sim gate: roster must be at or under the 15-standard limit */}
      {rosterOverflow && userTeam && (
        <div className="mb-6 p-5 rounded-xl border-2 border-red-500/60 bg-red-900/10">
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="font-semibold text-red-300 text-lg">⛔ Roster over the limit</div>
              <div className="text-sm text-zinc-300 mt-1">
                {userTeam} has <span className="font-mono font-bold">{standardCount}</span> standard contracts.
                The NBA max is 15. Release or trade <span className="font-mono font-bold">{standardCount! - 15}</span> player{standardCount! - 15 === 1 ? "" : "s"} before simming.
              </div>
            </div>
            <div className="flex gap-2 shrink-0">
              <Link href={`/team/${userTeam}`} className="px-3 py-2 rounded bg-zinc-800 hover:bg-zinc-700 text-sm">
                Release
              </Link>
              <Link href="/trade" className="px-3 py-2 rounded bg-orange-500 hover:bg-orange-400 text-black font-bold text-sm">
                → Open Trade Machine
              </Link>
            </div>
          </div>
        </div>
      )}

      {/* Roster preview — shown before sim runs so user sees final roster */}
      {!result && canSim && userTeam && (
        <RosterPreview tricode={userTeam} season={season} />
      )}

      {simError && (
        <div className="mb-4 p-4 rounded-lg border border-red-700 bg-red-900/20">
          <div className="font-semibold text-red-300 mb-1">Can&apos;t run sim</div>
          <div className="text-sm text-red-200">{simError}</div>
        </div>
      )}

      {!result && !simError && canSim && (
        <div className="text-center text-zinc-500 py-8 border border-dashed border-zinc-800 rounded-xl">
          When you&apos;re ready, hit &quot;Sim Season&quot; to play out {season}.
        </div>
      )}

      {result && (
        <>
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 mb-4">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-xs uppercase tracking-wider text-zinc-500">Champion</div>
                <div className="text-4xl font-bold text-orange-400 mt-1">{result.champion}</div>
                <div className="text-sm text-zinc-400 mt-1">Finals MVP: {result.finals_mvp}</div>
              </div>
              {userRecord && (
                <div className="text-right">
                  <div className="text-xs uppercase tracking-wider text-zinc-500">Your team ({userTeam})</div>
                  <div className="text-2xl font-bold mt-1">{userRecord.wins}-{userRecord.losses}</div>
                  <div className={`text-sm mt-1 ${userRecord.tricode === result.champion ? "text-orange-400 font-bold" : "text-zinc-400"}`}>
                    {EXIT_LABEL[userRecord.playoff_exit ?? ""] ?? "Missed playoffs"}
                  </div>
                </div>
              )}
            </div>
          </div>

          {season === "2026-27" && (
            <div className="bg-emerald-900/20 border border-emerald-700 rounded-xl p-5 mb-4 flex items-center justify-between">
              <div>
                <div className="font-semibold text-emerald-300">2026-27 season complete.</div>
                <div className="text-sm text-zinc-400 mt-1">
                  Process the 2027-28 offseason. Sequence: <span className="text-orange-300">1. Draft</span> →{" "}
                  <span className="text-orange-300">2. Options</span> →{" "}
                  <span className="text-orange-300">3. Free Agency &amp; Trades</span> →{" "}
                  <span className="text-orange-300">4. Sim 2027-28</span>.
                </div>
              </div>
              <button onClick={rollover} disabled={busy} className="px-4 py-2 rounded bg-emerald-600 hover:bg-emerald-500 text-white font-semibold disabled:opacity-50">
                → Start 2027-28 Offseason
              </button>
            </div>
          )}

          {season === "2027-28" && (
            <div className="bg-orange-900/20 border-2 border-orange-500 rounded-xl p-5 mb-4 flex items-center justify-between">
              <div>
                <div className="font-bold text-orange-300 text-lg">🏆 Game Complete!</div>
                <div className="text-sm text-zinc-400 mt-1">
                  You&apos;ve completed both the 2026-27 and 2027-28 seasons. Check the Awards page for the full history.
                </div>
              </div>
              <button onClick={startOver} disabled={busy} className="px-4 py-2 rounded bg-orange-500 hover:bg-orange-400 text-black font-bold disabled:opacity-50">
                ↻ Start Over from 2026 Offseason
              </button>
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6">
            <AwardCard label="MVP" name={result.mvp} team={result.mvp_team} />
            <AwardCard label="DPOY" name={result.dpoy} team={result.dpoy_team} />
            <AwardCard label="Rookie of the Year" name={result.roy} team={result.roy_team} fallback="(no rookies — run the draft first)" />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
            <Conference title="Eastern Conference" teams={east} seeds={result.east_seeds} userTeam={userTeam} />
            <Conference title="Western Conference" teams={west} seeds={result.west_seeds} userTeam={userTeam} />
          </div>

          {result.all_nba_first && result.all_nba_first.length > 0 && (
            <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
              <h2 className="text-lg font-semibold mb-3">All-NBA Teams</h2>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <AllNbaTeam label="First Team" players={result.all_nba_first} accent="orange" />
                <AllNbaTeam label="Second Team" players={result.all_nba_second} />
                <AllNbaTeam label="Third Team" players={result.all_nba_third} />
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function AwardCard({ label, name, team, fallback }: { label: string; name: string | null; team: string | null; fallback?: string }) {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
      <div className="text-xs uppercase tracking-wider text-zinc-500">{label}</div>
      <div className="text-lg font-bold mt-1">{name ?? "—"}</div>
      <div className="text-xs text-zinc-500">{team ?? fallback ?? ""}</div>
    </div>
  );
}

async function countUndrafted(year: number): Promise<number> {
  // Count undrafted picks by iterating; cheap because at most 60 picks
  try {
    const all = await api.draftOrder(year);
    return all.filter(p => p.pick_number && p.status === "OWNED").length;
  } catch {
    return 0;
  }
}

function AllNbaTeam({ label, players, accent }: { label: string; players: { name: string; team: string; ppg: number; rpg: number; apg: number }[]; accent?: string }) {
  return (
    <div className={`bg-zinc-950 border ${accent === "orange" ? "border-orange-500/40" : "border-zinc-800"} rounded p-3`}>
      <div className="text-xs uppercase tracking-wider text-zinc-500 mb-2">{label}</div>
      <ol className="space-y-1 text-sm">
        {players.map((p) => (
          <li key={p.name} className="flex items-center justify-between">
            <div>
              <span className="font-medium">{p.name}</span>{" "}
              <a href={`/team/${p.team}`} className="text-xs text-zinc-500 hover:text-orange-400">{p.team}</a>
            </div>
            <span className="text-xs text-zinc-400 font-mono">{p.ppg.toFixed(0)}/{p.rpg.toFixed(0)}/{p.apg.toFixed(0)}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

function Conference({ title, teams, seeds, userTeam }: {
  title: string;
  teams: SimResponse["standings"];
  seeds: string[];
  userTeam: string;
}) {
  const ordered = [...teams].sort((a, b) => b.wins - a.wins);
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg">
      <div className="px-5 py-3 border-b border-zinc-800">
        <h2 className="text-sm uppercase tracking-wider text-zinc-500">{title}</h2>
      </div>
      <table className="w-full text-sm">
        <thead className="text-xs uppercase tracking-wider text-zinc-500">
          <tr>
            <th className="text-left px-5 py-2 w-12">Seed</th>
            <th className="text-left px-5 py-2">Team</th>
            <th className="text-right px-5 py-2 w-20">Record</th>
            <th className="text-right px-5 py-2 w-32">Result</th>
          </tr>
        </thead>
        <tbody>
          {ordered.map((t) => {
            const seed = seeds.indexOf(t.tricode) + 1;
            const isUser = t.tricode === userTeam;
            return (
              <tr key={t.tricode} className={`border-t border-zinc-800/50 ${isUser ? "bg-orange-900/20" : seed > 0 && seed <= 6 ? "" : seed > 0 && seed <= 10 ? "bg-zinc-800/30" : "opacity-60"}`}>
                <td className="px-5 py-2 font-mono text-zinc-400">{seed > 0 ? seed : ""}</td>
                <td className="px-5 py-2 font-semibold">
                  <a href={`/team/${t.tricode}`} className="hover:text-orange-400 hover:underline">{t.tricode}</a>
                  {isUser && <span className="ml-2 text-xs text-orange-400">YOU</span>}
                </td>
                <td className="px-5 py-2 text-right font-mono">{t.wins}-{t.losses}</td>
                <td className="px-5 py-2 text-right text-xs">
                  {t.playoff_exit ? (
                    <span className={t.playoff_exit === "CHAMPION" ? "text-orange-400 font-bold" : "text-zinc-400"}>
                      {EXIT_LABEL[t.playoff_exit] ?? t.playoff_exit}
                    </span>
                  ) : (
                    <span className="text-zinc-600">—</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
