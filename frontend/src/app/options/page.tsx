"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api, fmt$, type PendingOption } from "@/lib/api";
import { useUserContext } from "@/lib/user-context";
import { useNextOffseasonStep } from "@/lib/use-next-step";
import { BackButton } from "@/app/back-button";

export default function OptionsPage() {
  const { team: userTeam, ready } = useUserContext();
  const next = useNextOffseasonStep("options");
  // Empty filter means "show only your team" by default.
  // Special "ALL" sentinel means user explicitly asked for the entire league.
  const [teamFilter, setTeamFilter] = useState<string>("");
  const [options, setOptions] = useState<PendingOption[]>([]);
  const [working, setWorking] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [season, setSeason] = useState<string>("2026-27");
  const [recent, setRecent] = useState<Array<{ id: number; description: string; cs_id: number; undone: boolean }>>([]);

  // Resolved filter that's actually sent to the API.
  const effectiveFilter = useMemo(() => {
    if (teamFilter === "ALL") return undefined;
    if (teamFilter) return teamFilter;
    return userTeam || undefined;
  }, [teamFilter, userTeam]);

  const load = async () => {
    if (!ready) return;
    try {
      const s = await api.state();
      setSeason(s.current_season);
      const r = await api.pendingOptions(effectiveFilter, s.current_season);
      setOptions(r);
      // Load recent option decisions for undo bar
      const txs = await api.recentTransactions(15, effectiveFilter);
      const optionTxs = txs
        .filter(t => t.type === "PICK_OPTION" && t.payload && ["EXERCISED", "DECLINED"].includes(String(t.payload["action"])))
        .map(t => ({
          id: t.id,
          description: t.description,
          cs_id: Number(t.payload["contract_season_id"]),
          undone: Boolean(t.payload["undone"]),
        }))
        .filter(x => !x.undone)
        .slice(0, 8);
      setRecent(optionTxs);
    } catch (e) {
      setError(String(e));
    }
  };

  useEffect(() => { load(); }, [effectiveFilter, ready]);

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

  const undo = async (cs_id: number) => {
    try {
      const r = await api.undoOption(cs_id);
      if (!r.ok) setError(r.error || "Undo failed");
      else await load();
    } catch (e) {
      setError(String(e));
    }
  };

  const playerOptions = options.filter(o => o.decided_by === "PLAYER");
  const teamOptions = options.filter(o => o.decided_by === "TEAM");

  const isFilteringMyTeam = !teamFilter && userTeam;
  const showingLabel = teamFilter === "ALL"
    ? "Showing entire league"
    : teamFilter
    ? `Showing ${teamFilter}`
    : userTeam
    ? `Showing your team (${userTeam})`
    : "Showing entire league";

  return (
    <div className="max-w-5xl mx-auto px-6 py-8">
      <BackButton />
      <div className="flex items-start justify-between mb-2 gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Option Decisions</h1>
          <p className="text-zinc-400 mt-1">
            Process player and team options for <span className="text-zinc-200 font-mono">{season}</span>.
            Declining either type sends the player to free agency.
          </p>
        </div>
        {userTeam && (
          <Link href={next.href} className="shrink-0 px-4 py-2 rounded-md bg-orange-500 hover:bg-orange-400 text-black font-semibold text-sm whitespace-nowrap">
            {next.label}
          </Link>
        )}
      </div>

      <div className="mb-4 flex items-center gap-3 flex-wrap">
        <div className="text-sm text-zinc-300">{showingLabel}</div>
        {isFilteringMyTeam && (
          <button
            onClick={() => setTeamFilter("ALL")}
            className="text-xs px-2.5 py-1 rounded border border-zinc-700 hover:bg-zinc-800 text-zinc-400"
          >
            Show entire league
          </button>
        )}
        {(teamFilter === "ALL" || (teamFilter && teamFilter !== userTeam)) && userTeam && (
          <button
            onClick={() => setTeamFilter("")}
            className="text-xs px-2.5 py-1 rounded bg-orange-500 text-black hover:bg-orange-400 font-medium"
          >
            Back to my team ({userTeam})
          </button>
        )}
        <label className="text-xs text-zinc-500 ml-2">Manual filter:</label>
        <input
          value={teamFilter === "ALL" ? "" : teamFilter}
          onChange={e => setTeamFilter(e.target.value.toUpperCase())}
          placeholder="LAL"
          className="bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-sm w-24 font-mono"
        />
        <div className="ml-auto text-xs text-zinc-500">
          {options.length} pending option{options.length !== 1 ? "s" : ""}
        </div>
      </div>

      {error && <div className="mb-4 p-3 rounded border border-red-800 bg-red-900/20 text-red-300 text-sm">{error}</div>}

      {recent.length > 0 && (
        <div className="mb-6 p-3 rounded border border-zinc-800 bg-zinc-900/60">
          <div className="flex items-center justify-between mb-2">
            <div className="text-xs uppercase tracking-wider text-zinc-500">Recent Decisions <span className="text-zinc-600">(click to undo)</span></div>
            <div className="text-xs text-zinc-600">{recent.length} undoable</div>
          </div>
          <ul className="space-y-1 text-sm">
            {recent.map(r => (
              <li key={r.id} className="flex items-center justify-between gap-3 py-1 border-b border-zinc-800/40 last:border-0">
                <div className="text-zinc-300 truncate">{r.description}</div>
                <button
                  onClick={() => undo(r.cs_id)}
                  className="text-xs px-2 py-0.5 rounded bg-zinc-800 hover:bg-orange-500 hover:text-black font-medium border border-zinc-700"
                >
                  ↶ Undo
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

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
          {isFilteringMyTeam
            ? `No pending options for ${userTeam}. Ready for free agency.`
            : "All options decided. Ready for free agency."}
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
