"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { BackButton } from "@/app/back-button";

type AllNbaPick = { name: string; team: string; position?: string };

type Award = {
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
  all_nba?: {
    first?: AllNbaPick[];
    second?: AllNbaPick[];
    third?: AllNbaPick[];
    all_defensive_first?: AllNbaPick[];
    all_defensive_second?: AllNbaPick[];
    all_rookie_first?: AllNbaPick[];
    all_rookie_second?: AllNbaPick[];
    six_man?: string | null;
    six_man_team?: string | null;
    mip?: string | null;
    mip_team?: string | null;
  };
};

export default function AwardsHistoryPage() {
  const [hist, setHist] = useState<Award[] | null>(null);

  useEffect(() => { api.awardsHistory().then(setHist).catch(() => setHist([])); }, []);

  if (hist === null) return <div className="max-w-4xl mx-auto px-6 py-8 text-zinc-500">Loading…</div>;

  return (
    <div className="max-w-4xl mx-auto px-6 py-8">
      <BackButton />
      <h1 className="text-3xl font-bold tracking-tight mb-2">Awards History</h1>
      <p className="text-zinc-400 mb-6">Champions, Finals MVPs, regular-season MVPs, DPOYs, ROYs across simulated seasons.</p>

      {hist.length === 0 ? (
        <div className="text-center text-zinc-500 py-16 border border-dashed border-zinc-800 rounded-xl">
          No seasons simulated yet. Sim a season to populate awards.
          <div className="mt-4"><Link href="/sim" className="px-4 py-2 rounded bg-orange-500 text-black font-semibold">Sim Season →</Link></div>
        </div>
      ) : (
        <div className="space-y-4">
          {hist.map((a) => (
            <div key={a.season} className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
              <div className="flex items-center justify-between mb-4">
                <div className="text-2xl font-bold">{a.season}</div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-zinc-500 uppercase tracking-wider">Champion</span>
                  <Link href={`/team/${a.champion}`} className="text-2xl font-bold text-orange-400 hover:underline">{a.champion ?? "—"}</Link>
                </div>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                <Award label="Finals MVP" name={a.finals_mvp} team={a.finals_mvp_team} accent="orange" />
                <Award label="MVP" name={a.mvp} team={a.mvp_team} />
                <Award label="DPOY" name={a.dpoy} team={a.dpoy_team} />
                <Award label="ROY" name={a.roy} team={a.roy_team} />
              </div>
              {(a.all_nba?.six_man || a.all_nba?.mip) && (
                <div className="grid grid-cols-2 gap-3 mb-4">
                  <Award label="6th Man" name={a.all_nba?.six_man ?? null} team={a.all_nba?.six_man_team ?? null} />
                  <Award label="Most Improved" name={a.all_nba?.mip ?? null} team={a.all_nba?.mip_team ?? null} />
                </div>
              )}
              {a.all_nba?.first && a.all_nba.first.length > 0 && (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-3 border-t border-zinc-800">
                  <AllNbaTeamCard label="All-NBA 1st" picks={a.all_nba.first} accent="orange" />
                  <AllNbaTeamCard label="All-NBA 2nd" picks={a.all_nba.second || []} />
                  <AllNbaTeamCard label="All-NBA 3rd" picks={a.all_nba.third || []} />
                </div>
              )}
              {a.all_nba?.all_defensive_first && a.all_nba.all_defensive_first.length > 0 && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-3 mt-3 border-t border-zinc-800">
                  <AllNbaTeamCard label="All-Defensive 1st" picks={a.all_nba.all_defensive_first} accent="orange" />
                  <AllNbaTeamCard label="All-Defensive 2nd" picks={a.all_nba.all_defensive_second || []} />
                </div>
              )}
              {a.all_nba?.all_rookie_first && a.all_nba.all_rookie_first.length > 0 && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-3 mt-3 border-t border-zinc-800">
                  <AllNbaTeamCard label="All-Rookie 1st" picks={a.all_nba.all_rookie_first} accent="orange" />
                  <AllNbaTeamCard label="All-Rookie 2nd" picks={a.all_nba.all_rookie_second || []} />
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function AllNbaTeamCard({ label, picks, accent }: { label: string; picks: AllNbaPick[]; accent?: string }) {
  return (
    <div className={`bg-zinc-950 border ${accent === "orange" ? "border-orange-500/40" : "border-zinc-800"} rounded p-3`}>
      <div className="text-xs uppercase tracking-wider text-zinc-500 mb-2">{label}</div>
      <ul className="space-y-0.5 text-xs">
        {picks.map((p) => (
          <li key={p.name} className="flex justify-between">
            <span><span className="text-zinc-500 w-6 inline-block">{p.position || ""}</span> {p.name}</span>
            <Link href={`/team/${p.team}`} className="text-zinc-500 hover:text-orange-400">{p.team}</Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Award({ label, name, team, accent }: { label: string; name: string | null; team: string | null; accent?: string }) {
  return (
    <div className={`bg-zinc-950 border ${accent === "orange" ? "border-orange-500/40" : "border-zinc-800"} rounded-lg p-3`}>
      <div className="text-xs uppercase tracking-wider text-zinc-500">{label}</div>
      <div className="font-bold mt-1">{name ?? "—"}</div>
      {team && <Link href={`/team/${team}`} className="text-xs text-zinc-400 hover:text-orange-400">{team}</Link>}
    </div>
  );
}
