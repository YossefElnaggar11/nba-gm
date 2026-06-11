"use client";

import { useEffect, useState } from "react";
import { api, type Roster } from "@/lib/api";

export function LastSeasonStats({ tricode }: { tricode: string }) {
  const [roster, setRoster] = useState<Roster | null>(null);
  useEffect(() => { api.roster(tricode).then(setRoster); }, [tricode]);
  if (!roster) return null;

  const withStats = roster.players.filter(p => p.last_season_stats && (p.last_season_stats.mpg ?? 0) > 0);
  if (withStats.length === 0) return null;

  withStats.sort((a, b) => (b.last_season_stats?.ppg ?? 0) - (a.last_season_stats?.ppg ?? 0));

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 mb-6">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold">
          2025-26 Stats <span className="text-xs text-zinc-500 font-normal">(prior season — for reference)</span>
        </h2>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-xs uppercase tracking-wider text-zinc-500 border-b border-zinc-800">
            <tr>
              <th className="text-left pb-2">Player</th>
              <th className="text-right pb-2 w-12">MPG</th>
              <th className="text-right pb-2 w-12">PPG</th>
              <th className="text-right pb-2 w-12">RPG</th>
              <th className="text-right pb-2 w-12">APG</th>
              <th className="text-right pb-2 w-12">SPG</th>
              <th className="text-right pb-2 w-12">BPG</th>
            </tr>
          </thead>
          <tbody>
            {withStats.map(p => {
              const s = p.last_season_stats!;
              return (
                <tr key={p.id} className="border-b border-zinc-800/40 last:border-0 hover:bg-zinc-800/30">
                  <td className="py-1.5">{p.name}</td>
                  <td className="text-right font-mono text-zinc-400">{s.mpg.toFixed(1)}</td>
                  <td className="text-right font-mono font-semibold">{s.ppg.toFixed(1)}</td>
                  <td className="text-right font-mono">{s.rpg.toFixed(1)}</td>
                  <td className="text-right font-mono">{s.apg.toFixed(1)}</td>
                  <td className="text-right font-mono">{s.spg.toFixed(1)}</td>
                  <td className="text-right font-mono">{s.bpg.toFixed(1)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
