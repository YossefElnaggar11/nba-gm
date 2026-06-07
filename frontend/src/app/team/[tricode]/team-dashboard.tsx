"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, fmt$, type PendingOption } from "@/lib/api";
import { useUserContext } from "@/lib/user-context";

type ResignFlow = {
  playerId: number;
  playerName: string;
  formerTeam: string;
  marketValue: number;
  minSalaryForYos: number;
  yos: number;
  overall: number | null;
  age: number | null;
} | null;

export function TeamDashboard({ viewTricode }: { viewTricode: string }) {
  const { team: userTeam, mode, ready } = useUserContext();
  const router = useRouter();
  const [options, setOptions] = useState<PendingOption[]>([]);
  const [working, setWorking] = useState<number | null>(null);
  const [resign, setResign] = useState<ResignFlow>(null);

  const isYour = ready && userTeam === viewTricode;

  const load = async () => {
    const r = await api.pendingOptions(viewTricode);
    setOptions(r);
  };
  useEffect(() => { if (isYour) load(); }, [isYour, viewTricode]);

  if (!ready) return null;
  if (!isYour) {
    return (
      <div className="bg-zinc-900/40 border border-zinc-800 rounded-lg p-4 mb-6 text-sm text-zinc-400 flex items-center justify-between">
        <div>
          You&apos;re viewing <span className="font-bold text-zinc-200">{viewTricode}</span> but you&apos;re GMing{" "}
          {userTeam ? <span className="font-bold text-orange-400">{userTeam}</span> : <span className="text-zinc-500">no team picked</span>}.
        </div>
        {userTeam ? (
          <Link href={`/team/${userTeam}`} className="text-xs px-3 py-1 rounded bg-zinc-800 hover:bg-zinc-700">
            ← Back to your team
          </Link>
        ) : (
          <Link href="/" className="text-xs px-3 py-1 rounded bg-orange-500 text-black font-medium hover:bg-orange-400">
            Pick a team
          </Link>
        )}
      </div>
    );
  }

  const pickup = async (id: number) => {
    setWorking(id);
    try {
      await api.decideOption(id, true);
      await load();
      router.refresh();
    } finally { setWorking(null); }
  };

  const sendToFA = async (id: number) => {
    setWorking(id);
    try {
      await api.decideOption(id, false, false);
      await load();
      router.refresh();
    } finally { setWorking(null); }
  };

  const declineAndResign = async (id: number) => {
    setWorking(id);
    try {
      const r = await api.decideOption(id, false, true);
      // Now find them in the FA pool to get the market value
      const fas = await api.freeAgents();
      const fa = fas.find(f => f.id === r.player_id);
      await load();
      router.refresh();
      if (fa) {
        setResign({
          playerId: r.player_id,
          playerName: r.player,
          formerTeam: r.former_team,
          marketValue: fa.market_value,
          minSalaryForYos: fa.min_salary_for_yos,
          yos: fa.years_of_service,
          overall: fa.overall,
          age: fa.age,
        });
      } else {
        alert(`${r.player} declined to free agency but couldn't load FA record. Try /free-agents to sign manually.`);
      }
    } finally { setWorking(null); }
  };

  const playerOpts = options.filter(o => o.decided_by === "PLAYER");
  const teamOpts = options.filter(o => o.decided_by === "TEAM");

  return (
    <>
      <div className="bg-gradient-to-br from-orange-900/20 to-zinc-900 border border-orange-500/40 rounded-xl p-5 mb-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <div className="text-xs uppercase tracking-wider text-orange-400 font-bold">GM Decisions</div>
            <p className="text-sm text-zinc-300 mt-1">
              Process options first, then sign FAs, run draft, sim season.
            </p>
          </div>
          <div className="flex gap-2 text-xs">
            <Link href="/options" className="px-3 py-1.5 rounded bg-zinc-800 hover:bg-zinc-700">All Options</Link>
            <Link href="/trade" className="px-3 py-1.5 rounded bg-zinc-800 hover:bg-zinc-700">Trade</Link>
            <Link href="/free-agents" className="px-3 py-1.5 rounded bg-zinc-800 hover:bg-zinc-700">Free Agents</Link>
            <Link href="/draft/2026/live" className="px-3 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500 text-white">Live Draft →</Link>
            <Link href="/sim" className="px-3 py-1.5 rounded bg-orange-500 hover:bg-orange-400 text-black font-medium">Sim Season →</Link>
          </div>
        </div>

        {options.length === 0 ? (
          <div className="text-sm text-zinc-500 italic">No pending option decisions for {viewTricode}.</div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <DecisionList
              title="Player Options"
              subtitle="Player decides. Most stars will opt out for bigger deals."
              options={playerOpts}
              onPickup={pickup}
              onSendToFA={sendToFA}
              onDeclineResign={declineAndResign}
              working={working}
            />
            <DecisionList
              title="Team Options"
              subtitle="You decide. Pick up, send to FA, or decline & re-sign on a new deal."
              options={teamOpts}
              onPickup={pickup}
              onSendToFA={sendToFA}
              onDeclineResign={declineAndResign}
              working={working}
              showResignOption
            />
          </div>
        )}
        {mode === "career" && (
          <div className="mt-4 text-xs text-zinc-500">
            Full GM Mode active: AI evaluates trade offers, FAs reject lowball signings.
          </div>
        )}
      </div>

      {resign && (
        <ResignModal
          flow={resign}
          onClose={() => setResign(null)}
          onDone={() => { setResign(null); router.refresh(); }}
        />
      )}
    </>
  );
}

function DecisionList({
  title, subtitle, options, onPickup, onSendToFA, onDeclineResign, working, showResignOption = true,
}: {
  title: string;
  subtitle: string;
  options: PendingOption[];
  onPickup: (id: number) => void;
  onSendToFA: (id: number) => void;
  onDeclineResign: (id: number) => void;
  working: number | null;
  showResignOption?: boolean;
}) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wider text-zinc-400">{title}</div>
      <div className="text-xs text-zinc-600 mb-2">{subtitle}</div>
      {options.length === 0 ? (
        <div className="text-xs text-zinc-600 italic py-2">None pending</div>
      ) : (
        <div className="space-y-1">
          {options.map(o => (
            <div key={o.contract_season_id} className="bg-zinc-950/60 rounded px-3 py-2 text-sm">
              <div className="flex items-center justify-between mb-1.5">
                <div>
                  <div className="font-medium">{o.player_name}</div>
                  <div className="text-xs text-zinc-500">{fmt$(o.salary)} for 2026-27</div>
                </div>
              </div>
              <div className="flex gap-1 flex-wrap">
                <button
                  disabled={working === o.contract_season_id}
                  onClick={() => onPickup(o.contract_season_id)}
                  className="px-2 py-0.5 text-xs rounded bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50"
                >
                  Pick up
                </button>
                <button
                  disabled={working === o.contract_season_id}
                  onClick={() => onSendToFA(o.contract_season_id)}
                  className="px-2 py-0.5 text-xs rounded bg-zinc-700 hover:bg-zinc-600 disabled:opacity-50"
                >
                  Send to FA
                </button>
                {showResignOption && (
                  <button
                    disabled={working === o.contract_season_id}
                    onClick={() => onDeclineResign(o.contract_season_id)}
                    className="px-2 py-0.5 text-xs rounded bg-orange-600 hover:bg-orange-500 disabled:opacity-50 text-white"
                  >
                    Decline &amp; Re-sign
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ResignModal({ flow, onClose, onDone }: { flow: NonNullable<ResignFlow>; onClose: () => void; onDone: () => void }) {
  const { mode } = useUserContext();
  // Default offer = max(vet-min for their YoS, market value). Ensures the offer is at
  // least legal under the min-salary floor. Round to nearest $100k for readability.
  const initialDefault = Math.max(flow.minSalaryForYos, flow.marketValue);
  const [salaryM, setSalaryM] = useState<number>(Math.round(initialDefault / 100_000) / 10);
  const [years, setYears] = useState(3);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await api.signPlayer({
        player_id: flow.playerId,
        team: flow.formerTeam,
        first_season: "2026-27",
        salary_year1: Math.round(salaryM * 1_000_000),
        years,
        using: "BIRD",
        apply: true,
        career_mode: mode === "career",
      });
      if (r.applied) {
        onDone();
      } else if (!r.valid) {
        setError(r.violations.map(v => v.message).join("\n"));
      } else if (!r.player_accepts) {
        setError(r.explanation || "Player rejected the offer.");
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur flex items-center justify-center p-4 z-50" onClick={onClose}>
      <div className="bg-zinc-900 border border-orange-500/40 rounded-xl p-6 w-full max-w-md" onClick={e => e.stopPropagation()}>
        <h2 className="text-xl font-semibold mb-1">Re-sign {flow.playerName}</h2>
        <div className="text-sm text-zinc-400 mb-1">
          OVR {flow.overall ?? "—"} · Age {flow.age ?? "—"} · {flow.yos}-yr vet · BIRD rights with {flow.formerTeam}
        </div>
        <div className="text-xs text-zinc-400 mb-4 space-y-0.5">
          <div>Market value: <span className="font-bold text-orange-300">{fmt$(flow.marketValue)}/yr</span></div>
          <div>Min salary (CBA floor for {flow.yos}-yr vet): <span className="font-mono">{fmt$(flow.minSalaryForYos)}</span></div>
          {mode === "career" && <div>Player accept floor: <span className="font-mono">{fmt$(Math.round(flow.marketValue * 0.75))}/yr</span></div>}
        </div>

        <div className="grid grid-cols-2 gap-3 mb-4">
          <div>
            <label className="block text-xs text-zinc-500 mb-1">Y1 Salary ($M)</label>
            <input type="number" step="0.1" value={salaryM} onChange={e => setSalaryM(parseFloat(e.target.value) || 0)} className="bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-sm w-full" />
          </div>
          <div>
            <label className="block text-xs text-zinc-500 mb-1">Years</label>
            <input type="number" min={1} max={5} value={years} onChange={e => setYears(parseInt(e.target.value) || 1)} className="bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-sm w-full" />
          </div>
        </div>

        {error && <div className="text-xs p-2 rounded bg-red-900/20 text-red-300 mb-3 whitespace-pre-line">{error}</div>}

        <div className="flex gap-2 justify-end">
          <button onClick={onClose} className="px-3 py-1.5 text-sm rounded bg-zinc-800 hover:bg-zinc-700">Cancel</button>
          <button disabled={busy} onClick={submit} className="px-3 py-1.5 text-sm rounded bg-orange-500 hover:bg-orange-400 text-black font-medium">
            {busy ? "Signing…" : "Sign"}
          </button>
        </div>
      </div>
    </div>
  );
}
