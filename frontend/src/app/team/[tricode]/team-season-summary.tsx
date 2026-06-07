"use client";

import { useEffect, useState } from "react";

type SeasonSummary = {
  season: string;
  wins: number;
  losses: number;
  seed: number | null;
  made_playoffs: boolean;
  playoff_exit_round: string | null;
};

type SeasonAward = {
  season: string;
  champion: string | null;
  finals_mvp: string | null;
  finals_mvp_team: string | null;
  mvp: string | null;
  mvp_team: string | null;
  dpoy: string | null;
  dpoy_team: string | null;
  roy: string | null;
  roy_team: string | null;
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8765";

const EXIT: Record<string, string> = {
  R1: "Lost R1", R2: "Lost R2", CONF_FINALS: "Lost CF",
  FINALS: "Lost Finals", CHAMPION: "🏆 CHAMPION",
};

export function TeamSeasonSummary({ tricode }: { tricode: string }) {
  const [summaries, setSummaries] = useState<SeasonSummary[]>([]);
  const [awards, setAwards] = useState<SeasonAward[]>([]);

  useEffect(() => {
    fetch(`${API_BASE}/api/sim/awards-history`, { cache: "no-store" })
      .then(r => r.json())
      .then(async (hist: SeasonAward[]) => {
        setAwards(hist);
        // For each simmed season, fetch standings for this team
        const summs = await Promise.all(
          hist.map(async (h) => {
            try {
              const s = await fetch(`${API_BASE}/api/sim/standings/${h.season}`, { cache: "no-store" }).then(r => r.json());
              const my = s.teams.find((t: SeasonSummary & { tricode: string }) => t.tricode === tricode);
              return my ? { ...my, season: h.season } : null;
            } catch { return null; }
          })
        );
        setSummaries(summs.filter(Boolean) as SeasonSummary[]);
      });
  }, [tricode]);

  if (summaries.length === 0) return null;

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 mb-6">
      <h2 className="text-lg font-semibold mb-3">Simulated Seasons</h2>
      <div className="space-y-2">
        {summaries.map((s) => {
          const aw = awards.find((a) => a.season === s.season);
          const teamAwards: string[] = [];
          if (aw?.champion === tricode) teamAwards.push("🏆 CHAMPION");
          if (aw?.mvp_team === tricode) teamAwards.push(`MVP: ${aw.mvp}`);
          if (aw?.finals_mvp_team === tricode) teamAwards.push(`Finals MVP: ${aw.finals_mvp}`);
          if (aw?.dpoy_team === tricode) teamAwards.push(`DPOY: ${aw.dpoy}`);
          if (aw?.roy_team === tricode) teamAwards.push(`ROY: ${aw.roy}`);
          return (
            <div key={s.season} className="flex items-center justify-between border-b border-zinc-800/50 last:border-0 pb-2 last:pb-0">
              <div>
                <div className="font-semibold text-sm">{s.season}</div>
                <div className="text-xs text-zinc-500">
                  {s.wins}-{s.losses}{s.seed ? ` · Seed ${s.seed}` : ""} · {s.playoff_exit_round ? EXIT[s.playoff_exit_round] ?? s.playoff_exit_round : "Missed playoffs"}
                </div>
              </div>
              {teamAwards.length > 0 && (
                <div className="flex flex-wrap gap-2 justify-end max-w-md">
                  {teamAwards.map((a, i) => (
                    <span key={i} className={`text-xs px-2 py-0.5 rounded ${a.startsWith("🏆") ? "bg-orange-900/40 text-orange-300 font-semibold" : "bg-zinc-800 text-zinc-300"}`}>{a}</span>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
