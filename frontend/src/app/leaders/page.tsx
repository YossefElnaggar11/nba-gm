"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";

type Leader = { name: string; team: string; value: number; gp: number };

export default function LeadersPage() {
  const [season, setSeason] = useState("2026-27");
  const [data, setData] = useState<{
    ppg: Leader[]; rpg: Leader[]; apg: Leader[]; spg: Leader[]; bpg: Leader[];
  } | null>(null);
  const [seasons, setSeasons] = useState<string[]>([]);

  useEffect(() => {
    api.awardsHistory().then(hist => {
      const s = hist.map(h => h.season);
      setSeasons(s);
      if (s.length > 0) setSeason(s[s.length - 1]);
    });
  }, []);

  useEffect(() => {
    if (season) api.leaders(season).then(setData);
  }, [season]);

  return (
    <div className="max-w-5xl mx-auto px-6 py-8">
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">League Leaders</h1>
          <p className="text-zinc-400 mt-1">Top stat producers in {season}.</p>
        </div>
        {seasons.length > 1 && (
          <select value={season} onChange={e => setSeason(e.target.value)} className="bg-zinc-800 border border-zinc-700 rounded px-3 py-1.5 text-sm">
            {seasons.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        )}
      </div>

      {!data || (data.ppg.length === 0) ? (
        <div className="text-center text-zinc-500 py-16 border border-dashed border-zinc-800 rounded-xl">
          No stats for {season}. Sim a season first.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <LeaderCard title="Points / Game" data={data.ppg} fmt={v => v.toFixed(1)} />
          <LeaderCard title="Rebounds / Game" data={data.rpg} fmt={v => v.toFixed(1)} />
          <LeaderCard title="Assists / Game" data={data.apg} fmt={v => v.toFixed(1)} />
          <LeaderCard title="Steals / Game" data={data.spg} fmt={v => v.toFixed(1)} />
          <LeaderCard title="Blocks / Game" data={data.bpg} fmt={v => v.toFixed(1)} />
        </div>
      )}
    </div>
  );
}

function LeaderCard({ title, data, fmt }: { title: string; data: Leader[]; fmt: (v: number) => string }) {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
      <h2 className="text-sm uppercase tracking-wider text-zinc-500 mb-2">{title}</h2>
      <ol className="space-y-1 text-sm">
        {data.slice(0, 10).map((p, i) => (
          <li key={p.name + p.team} className="flex items-center justify-between border-b border-zinc-800/30 last:border-0 pb-1 last:pb-0">
            <div className="flex items-center gap-2">
              <span className="text-xs text-zinc-500 w-4 text-right">{i + 1}.</span>
              <span className="truncate">{p.name}</span>
              <Link href={`/team/${p.team}`} className="text-xs text-zinc-500 hover:text-orange-400">{p.team}</Link>
            </div>
            <span className="font-mono font-bold">{fmt(p.value)}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
