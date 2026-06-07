"use client";

import { useEffect, useState } from "react";
import { api, fmt$, type PendingOption } from "@/lib/api";
import { PhaseNav, NextPhaseButton } from "@/app/phase-nav";
import { useUserContext } from "@/lib/user-context";

export default function OptionsPage() {
  const { team: userTeam } = useUserContext();
  const [teamFilter, setTeamFilter] = useState<string>("");
  const [options, setOptions] = useState<PendingOption[]>([]);
  const [working, setWorking] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [season, setSeason] = useState<string>("2026-27");

  const load = async () => {
    try {
      const s = await api.state();
      setSeason(s.current_season);
      const r = await api.pendingOptions(teamFilter || undefined, s.current_season);
      setOptions(r);
    } catch (e) {
      setError(String(e));
    }
  };

  useEffect(() => { load(); }, [teamFilter]);
  useEffect(() => {
    // Default the filter to user's team so options list is focused
    if (userTeam && !teamFilter) setTeamFilter(userTeam);
  }, [userTeam]);

  const decide = async (id: number, pickUp: boolean) => {
    setWorking(id);
    try {
      await api.decideOption(id, pickUp);
      await load();
    } catch (e) {
      setError(String(e));
    } finally {
      setWorking(null);
    }
  };

  const playerOptions = options.filter(o => o.decided_by === "PLAYER");
  const teamOptions = options.filter(o => o.decided_by === "TEAM");

  return (
    <div className="max-w-5xl mx-auto px-6 py-8">
      <PhaseNav />
      <div className="flex items-start justify-between mb-2">
        <h1 className="text-3xl font-bold tracking-tight">Option Decisions</h1>
        <NextPhaseButton from="options" />
      </div>
      <p className="text-zinc-400 mb-6">
        Process player and team options for <span className="text-zinc-200 font-mono">{season}</span>.
        Declining either type sends the player to free agency.
      </p>

      <div className="mb-4 flex items-center gap-3">
        <label className="text-sm text-zinc-400">Filter by team:</label>
        <input
          value={teamFilter}
          onChange={e => setTeamFilter(e.target.value.toUpperCase())}
          placeholder="LAL"
          className="bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-sm w-24 font-mono"
        />
        {teamFilter && (
          <button onClick={() => setTeamFilter("")} className="text-xs text-zinc-500 hover:text-zinc-300">clear</button>
        )}
        <div className="ml-auto text-xs text-zinc-500">
          {options.length} pending option{options.length !== 1 ? "s" : ""}
        </div>
      </div>

      {error && <div className="mb-4 p-3 rounded border border-red-800 bg-red-900/20 text-red-300 text-sm">{error}</div>}

      <Section
        title="Player Options"
        subtitle="Player decides — usually they pick up if option > their expected market, decline if they can get more"
        options={playerOptions}
        onDecide={decide}
        working={working}
      />
      <Section
        title="Team Options"
        subtitle="Team decides — pick up if player is worth the salary, decline to make them an FA"
        options={teamOptions}
        onDecide={decide}
        working={working}
      />

      {options.length === 0 && (
        <div className="text-center text-zinc-500 py-12">
          All options decided. Ready for free agency.
        </div>
      )}
    </div>
  );
}

function Section({ title, subtitle, options, onDecide, working }: {
  title: string;
  subtitle: string;
  options: PendingOption[];
  onDecide: (id: number, pickUp: boolean) => void;
  working: number | null;
}) {
  if (!options.length) return null;
  return (
    <div className="mb-8">
      <h2 className="text-sm uppercase tracking-wider text-zinc-500">{title}</h2>
      <p className="text-xs text-zinc-600 mb-3">{subtitle}</p>
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-zinc-800/50 text-xs uppercase tracking-wider text-zinc-500">
            <tr>
              <th className="text-left px-4 py-2">Player</th>
              <th className="text-left px-4 py-2 w-20">Team</th>
              <th className="text-right px-4 py-2 w-32">Salary</th>
              <th className="text-right px-4 py-2 w-72">Decision</th>
            </tr>
          </thead>
          <tbody>
            {options.map(o => (
              <tr key={o.contract_season_id} className="border-t border-zinc-800/50">
                <td className="px-4 py-2 font-medium">{o.player_name}</td>
                <td className="px-4 py-2 text-zinc-400 font-mono">{o.team}</td>
                <td className="px-4 py-2 text-right font-mono">{fmt$(o.salary)}</td>
                <td className="px-4 py-2 text-right">
                  <button
                    disabled={working === o.contract_season_id}
                    onClick={() => onDecide(o.contract_season_id, true)}
                    className="px-2 py-1 mr-2 text-xs rounded bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50"
                  >
                    Pick up
                  </button>
                  <button
                    disabled={working === o.contract_season_id}
                    onClick={() => onDecide(o.contract_season_id, false)}
                    className="px-2 py-1 text-xs rounded bg-zinc-700 hover:bg-zinc-600 disabled:opacity-50"
                  >
                    Decline → FA
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
