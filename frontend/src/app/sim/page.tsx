"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type SimResponse } from "@/lib/api";
import { PhaseNav } from "@/app/phase-nav";
import { useUserContext } from "@/lib/user-context";

const EXIT_LABEL: Record<string, string> = {
  R1: "Lost R1",
  R2: "Lost R2",
  CONF_FINALS: "Lost CF",
  FINALS: "Lost Finals",
  CHAMPION: "🏆 CHAMPION",
};

export default function SimPage() {
  const { team: userTeamCtx, mode } = useUserContext();
  const [season, setSeason] = useState("2026-27");
  const [userTeam, setUserTeam] = useState("LAL");
  const [result, setResult] = useState<SimResponse | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (userTeamCtx) setUserTeam(userTeamCtx);
    // Default season to current state's season
    api.state().then(s => setSeason(s.current_season)).catch(() => {});
  }, [userTeamCtx]);

  if (mode === "offseason") {
    return (
      <div className="max-w-2xl mx-auto px-6 py-12 text-center">
        <PhaseNav />
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
    try {
      const r = await api.simSeason(season);
      setResult(r);
    } finally {
      setBusy(false);
    }
  };

  const rollover = async () => {
    if (!result) return;
    const nextSeason = season === "2026-27" ? "2027-28" : "2028-29";
    if (!confirm(`Advance from ${season} to ${nextSeason}? Contracts ending this year release players to free agency, players age +1, young players develop, vets decline. You'll then run the 2027-28 offseason (options, FA, draft).`)) return;
    setBusy(true);
    try {
      const r = await api.rollover(season, nextSeason);
      alert(`Rolled over to ${nextSeason}!\n${r.contracts_dropped} contracts expired, ${r.new_free_agents} new FAs.\nNow process options and free agents for ${nextSeason}.`);
      setSeason(nextSeason);
      setResult(null);
      // Navigate user back to options/team page so they cycle through the next offseason
      window.location.href = "/options";
    } finally {
      setBusy(false);
    }
  };

  const east = result?.standings.filter(s => s.conference === "East") ?? [];
  const west = result?.standings.filter(s => s.conference === "West") ?? [];
  const userRecord = result?.standings.find(s => s.tricode === userTeam);

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      <PhaseNav />
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Season Simulation</h1>
          <p className="text-zinc-400 mt-1">
            Regular season (82 games per team) + 16-team playoff bracket. Re-runs replace prior results.
          </p>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <select value={season} onChange={e => setSeason(e.target.value)} className="bg-zinc-800 border border-zinc-700 rounded px-2 py-1">
            <option value="2026-27">2026-27</option>
            <option value="2027-28">2027-28</option>
          </select>
          <button onClick={sim} disabled={busy} className="px-4 py-2 rounded bg-orange-500 hover:bg-orange-400 text-black font-semibold disabled:opacity-50">
            {busy ? "Simulating…" : "Sim Season"}
          </button>
        </div>
      </div>

      {!result && (
        <div className="text-center text-zinc-500 py-16 border border-dashed border-zinc-800 rounded-xl">
          Hit &quot;Sim Season&quot; to play out {season}.
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

          {/* Advance to next offseason CTA (only if not last simmed season in scope) */}
          {season !== "2028-29" && (
            <div className="bg-emerald-900/20 border border-emerald-700 rounded-xl p-5 mb-4 flex items-center justify-between">
              <div>
                <div className="font-semibold text-emerald-300">{season} complete.</div>
                <div className="text-sm text-zinc-400 mt-1">
                  Process the next offseason: option decisions, FA signings, the {parseInt(season.split("-")[0]) + 1} draft (lottery already set above).
                </div>
              </div>
              <button onClick={rollover} disabled={busy} className="px-4 py-2 rounded bg-emerald-600 hover:bg-emerald-500 text-white font-semibold disabled:opacity-50">
                → Start {parseInt(season.split("-")[0]) + 1}-{(parseInt(season.split("-")[0]) + 2).toString().slice(2)} Offseason
              </button>
            </div>
          )}

          {/* Awards strip */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6">
            <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
              <div className="text-xs uppercase tracking-wider text-zinc-500">MVP</div>
              <div className="text-lg font-bold mt-1">{result.mvp ?? "—"}</div>
              <div className="text-xs text-zinc-500">{result.mvp_team ?? ""}</div>
            </div>
            <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
              <div className="text-xs uppercase tracking-wider text-zinc-500">DPOY</div>
              <div className="text-lg font-bold mt-1">{result.dpoy ?? "—"}</div>
              <div className="text-xs text-zinc-500">{result.dpoy_team ?? ""}</div>
            </div>
            <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
              <div className="text-xs uppercase tracking-wider text-zinc-500">Rookie of the Year</div>
              <div className="text-lg font-bold mt-1">{result.roy ?? "—"}</div>
              <div className="text-xs text-zinc-500">{result.roy_team ?? "(no rookies — run the draft first)"}</div>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
            <Conference title="Eastern Conference" teams={east} seeds={result.east_seeds} userTeam={userTeam} />
            <Conference title="Western Conference" teams={west} seeds={result.west_seeds} userTeam={userTeam} />
          </div>

          {/* All-NBA teams */}
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

function AllNbaTeam({ label, players, accent }: { label: string; players: { name: string; team: string; ppg: number; rpg: number; apg: number }[]; accent?: string }) {
  return (
    <div className={`bg-zinc-950 border ${accent === "orange" ? "border-orange-500/40" : "border-zinc-800"} rounded p-3`}>
      <div className="text-xs uppercase tracking-wider text-zinc-500 mb-2">{label}</div>
      <ol className="space-y-1 text-sm">
        {players.map((p, i) => (
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
          {ordered.map((t, idx) => {
            const seed = seeds.indexOf(t.tricode) + 1;
            const isUser = t.tricode === userTeam;
            return (
              <tr key={t.tricode} className={`border-t border-zinc-800/50 ${isUser ? "bg-orange-900/20" : seed <= 6 ? "" : seed <= 10 ? "bg-zinc-800/30" : "opacity-60"}`}>
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
