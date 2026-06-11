"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, fmt$, fmt$Full, type CapSheet, type Roster } from "@/lib/api";

/**
 * Final-roster preview component. Shows the team's complete roster going into
 * the season — with all contracts (incl. rookie scale for drafted players),
 * total cap impact, and apron status. Used as the "before you sim" view.
 */
export function RosterPreview({ tricode, season }: { tricode: string; season: string }) {
  const [cap, setCap] = useState<CapSheet | null>(null);
  const [roster, setRoster] = useState<Roster | null>(null);

  useEffect(() => {
    Promise.all([api.capSheet(tricode, season), api.roster(tricode)]).then(([c, r]) => {
      setCap(c);
      setRoster(r);
    });
  }, [tricode, season]);

  if (!cap || !roster) return null;

  // Group players by salary bucket
  const stars = cap.players.filter(p => p.salary >= 20_000_000);
  const starters = cap.players.filter(p => p.salary >= 5_000_000 && p.salary < 20_000_000);
  const rotation = cap.players.filter(p => p.salary >= 2_000_000 && p.salary < 5_000_000);
  const minimums = cap.players.filter(p => p.salary < 2_000_000);

  // Identify rookie-scale contracts (any player on signed_using=ROOKIE_SCALE via contract).
  // Since cap sheet flattens, we infer from low salary + young age + recent contract; mainly informational here.

  return (
    <div className="bg-zinc-900 border-2 border-orange-500/40 rounded-xl p-5 mb-6">
      <div className="flex items-center justify-between mb-4">
        <div>
          <div className="text-xs uppercase tracking-wider text-orange-400 font-bold">Final Roster — {season}</div>
          <h2 className="text-xl font-bold mt-1">Going into the season</h2>
          <p className="text-xs text-zinc-500 mt-1">
            {cap.players.length} players under contract · all signings, trades, draft picks, and option decisions applied
          </p>
        </div>
        <div className="text-right">
          <div className="text-xs uppercase text-zinc-500">Total Payroll</div>
          <div className="text-2xl font-mono font-bold">{fmt$(cap.total_salary)}</div>
          <div className={`text-xs mt-1 ${
            cap.over_second_apron ? "text-red-400" :
            cap.over_first_apron ? "text-orange-400" :
            cap.over_tax ? "text-yellow-400" :
            cap.cap_space > 0 ? "text-emerald-400" : "text-zinc-400"
          }`}>
            {cap.over_second_apron ? "Above 2nd Apron" :
             cap.over_first_apron ? "Above 1st Apron" :
             cap.over_tax ? "Over Luxury Tax" :
             cap.cap_space > 0 ? `${fmt$(cap.cap_space)} of cap space` : "Over the cap"}
          </div>
        </div>
      </div>

      <RosterGroup label="Stars ($20M+)" players={stars} />
      <RosterGroup label="Starters / Mid Salary ($5M-$20M)" players={starters} />
      <RosterGroup label="Rotation ($2M-$5M)" players={rotation} />
      <RosterGroup label="Minimums / Rookie Scale (<$2M)" players={minimums} />

      {roster.count > cap.players.length && (
        <div className="text-xs text-zinc-500 mt-3">
          Note: {roster.count - cap.players.length} additional roster spots open (two-way, unsigned, or pending FA signings)
        </div>
      )}

      <div className="mt-4 pt-4 border-t border-zinc-800 flex items-center justify-between">
        <Link href={`/team/${tricode}`} className="text-xs text-zinc-400 hover:text-orange-400">
          ← Make more moves
        </Link>
        <div className="text-xs text-zinc-500">
          Once you&apos;re ready, head to <Link href="/sim" className="text-orange-400 hover:underline">Sim Season</Link>
        </div>
      </div>
    </div>
  );
}

function RosterGroup({ label, players }: { label: string; players: CapSheet["players"] }) {
  if (!players.length) return null;
  return (
    <div className="mb-3">
      <div className="text-xs uppercase tracking-wider text-zinc-500 mb-1">{label} <span className="text-zinc-600">({players.length})</span></div>
      <div className="bg-zinc-950 rounded border border-zinc-800">
        <table className="w-full text-sm">
          <tbody>
            {players.map((p) => (
              <tr key={p.player_id} className="border-b border-zinc-800/40 last:border-0">
                <td className="px-3 py-1.5">{p.name}</td>
                <td className="px-3 py-1.5 text-right text-zinc-400 w-12">{p.age ?? "—"}</td>
                <td className="px-3 py-1.5 text-right font-mono w-32">{fmt$Full(p.salary)}</td>
                <td className="px-3 py-1.5 text-right w-24">
                  {p.option_type === "PLAYER" && <span className="text-xs px-1.5 py-0.5 rounded bg-yellow-900/40 text-yellow-400">P-OPT</span>}
                  {p.option_type === "TEAM" && <span className="text-xs px-1.5 py-0.5 rounded bg-blue-900/40 text-blue-400">T-OPT</span>}
                  {!p.guaranteed && <span className="text-xs ml-1 px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400">non-gtd</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
