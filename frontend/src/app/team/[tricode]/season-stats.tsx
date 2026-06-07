"use client";

import { useEffect, useState } from "react";

type PlayerStat = {
  player_id: number;
  name: string;
  age: number | null;
  position: string | null;
  overall: number | null;
  games_played: number;
  games_started: number;
  mpg: number;
  ppg: number;
  rpg: number;
  apg: number;
  spg: number;
  bpg: number;
  fg_pct: number;
  three_pct: number;
  ft_pct: number;
  is_injured: boolean;
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8765";

export function SeasonStats({ tricode }: { tricode: string }) {
  const [players, setPlayers] = useState<PlayerStat[] | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [season, setSeason] = useState<string>("2026-27");
  const [availableSeasons, setAvailableSeasons] = useState<string[]>([]);

  useEffect(() => {
    fetch(`${API_BASE}/api/state`, { cache: "no-store" })
      .then(r => r.json())
      .then(s => setAvailableSeasons(s.simmed_seasons || []));
  }, []);

  useEffect(() => {
    if (availableSeasons.length > 0 && !availableSeasons.includes(season)) {
      setSeason(availableSeasons[availableSeasons.length - 1]);
    }
  }, [availableSeasons]);

  useEffect(() => {
    fetch(`${API_BASE}/api/stats/team/${tricode}/${season}`, { cache: "no-store" })
      .then(r => r.json())
      .then(d => {
        setPlayers(d.players || []);
        setNote(d.note || null);
      });
  }, [tricode, season]);

  if (players === null) return null;

  if (!players.length) {
    return (
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 mb-6">
        <h2 className="text-lg font-semibold mb-2">Player Stats</h2>
        <p className="text-sm text-zinc-500">{note || "No simulated stats yet. Run a season sim first (Full GM Mode)."}</p>
      </div>
    );
  }

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 mb-6">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold">Player Stats <span className="text-xs text-zinc-500 font-normal">(simulated)</span></h2>
        {availableSeasons.length > 1 && (
          <select value={season} onChange={e => setSeason(e.target.value)} className="bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-xs">
            {availableSeasons.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        )}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-xs uppercase tracking-wider text-zinc-500 border-b border-zinc-800">
            <tr>
              <th className="text-left pb-2">Player</th>
              <th className="text-right pb-2 w-12">OVR</th>
              <th className="text-right pb-2 w-12">GP</th>
              <th className="text-right pb-2 w-12">MPG</th>
              <th className="text-right pb-2 w-12">PPG</th>
              <th className="text-right pb-2 w-12">RPG</th>
              <th className="text-right pb-2 w-12">APG</th>
              <th className="text-right pb-2 w-12">SPG</th>
              <th className="text-right pb-2 w-12">BPG</th>
              <th className="text-right pb-2 w-14">FG%</th>
              <th className="text-right pb-2 w-14">3P%</th>
            </tr>
          </thead>
          <tbody>
            {players.map(p => (
              <tr key={p.player_id} className="border-b border-zinc-800/50 hover:bg-zinc-800/30">
                <td className="py-1.5">
                  {p.name}
                  {p.is_injured && <span className="ml-2 text-xs px-1.5 py-0.5 rounded bg-red-900/40 text-red-300">INJ</span>}
                </td>
                <td className="text-right text-zinc-400 font-mono">{p.overall ?? "—"}</td>
                <td className="text-right text-zinc-400 font-mono">{p.games_played}</td>
                <td className="text-right font-mono">{p.mpg.toFixed(1)}</td>
                <td className="text-right font-mono font-semibold">{p.ppg.toFixed(1)}</td>
                <td className="text-right font-mono">{p.rpg.toFixed(1)}</td>
                <td className="text-right font-mono">{p.apg.toFixed(1)}</td>
                <td className="text-right font-mono">{p.spg.toFixed(1)}</td>
                <td className="text-right font-mono">{p.bpg.toFixed(1)}</td>
                <td className="text-right font-mono text-zinc-400">{(p.fg_pct * 100).toFixed(1)}</td>
                <td className="text-right font-mono text-zinc-400">{(p.three_pct * 100).toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
