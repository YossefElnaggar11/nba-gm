"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, fmt$, type OwnFA } from "@/lib/api";
import { useUserContext } from "@/lib/user-context";
import { getAiVetoDisabled } from "@/lib/ai-veto";

/**
 * "Your Free Agents" panel — shows players the team has Bird rights to (i.e.,
 * they're FAs but the team holds a cap hold for them). Lets you re-sign with
 * Bird rights or renounce.
 */
export function OwnFreeAgents({ tricode }: { tricode: string }) {
  const { team: userTeam, mode } = useUserContext();
  const router = useRouter();
  const [fas, setFAs] = useState<OwnFA[]>([]);
  const [resign, setResign] = useState<OwnFA | null>(null);

  const load = () => {
    api.ownFAs(tricode).then(r => setFAs(r.own_fas));
  };
  useEffect(() => { load(); }, [tricode]);

  if (fas.length === 0) return null;

  // Group by RFA vs UFA
  const rfa = fas.filter(f => f.fa_type === "RFA");
  const ufa = fas.filter(f => f.fa_type !== "RFA");

  const renounce = async (hold_id: number, name: string) => {
    if (!confirm(`Renounce ${name}? You'll lose Bird rights and the cap hold will be cleared.`)) return;
    await api.renounceHold(hold_id);
    load();
    router.refresh();
  };

  const isYourTeam = userTeam === tricode;

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 mb-6">
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-lg font-semibold">
          Your Free Agents <span className="text-xs text-zinc-500 font-normal">({fas.length})</span>
        </h2>
        <span className="text-xs text-zinc-500">Bird rights — you can re-sign over the cap</span>
      </div>

      {ufa.length > 0 && (
        <FASection title="Unrestricted FAs (Bird Rights)" subtitle="They can sign anywhere, but you can offer more years and higher raises than other teams." fas={ufa} onResign={isYourTeam ? setResign : undefined} onRenounce={isYourTeam ? renounce : undefined} />
      )}
      {rfa.length > 0 && (
        <FASection title="Restricted FAs" subtitle="If another team signs them to an offer sheet, you have 48 hours to match." fas={rfa} onResign={isYourTeam ? setResign : undefined} onRenounce={isYourTeam ? renounce : undefined} />
      )}

      {resign && (
        <ResignModal fa={resign} tricode={tricode} mode={mode} onClose={() => setResign(null)} onDone={() => { setResign(null); load(); router.refresh(); }} />
      )}
    </div>
  );
}

function FASection({ title, subtitle, fas, onResign, onRenounce }: {
  title: string;
  subtitle: string;
  fas: OwnFA[];
  onResign?: (fa: OwnFA) => void;
  onRenounce?: (hold_id: number, name: string) => void;
}) {
  return (
    <div className="mb-4 last:mb-0">
      <div className="text-xs uppercase tracking-wider text-zinc-500 mt-2">{title}</div>
      <div className="text-xs text-zinc-600 mb-2">{subtitle}</div>
      <div className="bg-zinc-950 rounded border border-zinc-800">
        <table className="w-full text-sm">
          <thead className="text-xs uppercase tracking-wider text-zinc-500 border-b border-zinc-800">
            <tr>
              <th className="text-left px-3 py-2">Player</th>
              <th className="text-right px-3 py-2 w-12">OVR</th>
              <th className="text-right px-3 py-2 w-12">Age</th>
              <th className="text-left px-3 py-2 w-12">Pos</th>
              <th className="text-right px-3 py-2 w-32">Cap Hold</th>
              <th className="text-right px-3 py-2 w-28">Market ~$/yr</th>
              <th className="text-right px-3 py-2 w-40"></th>
            </tr>
          </thead>
          <tbody>
            {fas.map(f => (
              <tr key={f.hold_id} className="border-b border-zinc-800/40 last:border-0">
                <td className="px-3 py-1.5 font-medium">{f.name}</td>
                <td className="px-3 py-1.5 text-right text-zinc-400 font-mono">{f.overall ?? "—"}</td>
                <td className="px-3 py-1.5 text-right text-zinc-400">{f.age ?? "—"}</td>
                <td className="px-3 py-1.5 text-zinc-400">{f.position ?? "—"}</td>
                <td className="px-3 py-1.5 text-right font-mono">{fmt$(f.hold_amount)}</td>
                <td className="px-3 py-1.5 text-right text-orange-300 font-mono">{fmt$(f.market_value)}</td>
                <td className="px-3 py-1.5 text-right">
                  {onResign && (
                    <button onClick={() => onResign(f)} className="px-2 py-0.5 text-xs rounded bg-emerald-700 hover:bg-emerald-600 mr-1">
                      Re-sign (Bird)
                    </button>
                  )}
                  {onRenounce && (
                    <button onClick={() => onRenounce(f.hold_id, f.name)} className="px-2 py-0.5 text-xs rounded bg-zinc-700 hover:bg-zinc-600">
                      Renounce
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ResignModal({ fa, tricode, mode, onClose, onDone }: {
  fa: OwnFA;
  tricode: string;
  mode: "career" | "offseason";
  onClose: () => void;
  onDone: () => void;
}) {
  // Default to MIN legal salary — user negotiates up from there
  const [salaryM, setSalaryM] = useState(Math.round(fa.min_salary / 100_000) / 10);
  const [years, setYears] = useState(3);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await api.signPlayer({
        player_id: fa.player_id,
        team: tricode,
        first_season: "2026-27",
        salary_year1: Math.round(salaryM * 1_000_000),
        years,
        using: "BIRD",
        apply: true,
        career_mode: mode === "career" && !getAiVetoDisabled(),
      });
      if (r.applied) onDone();
      else if (!r.valid) setError(r.violations.map(v => v.message).join("\n"));
      else if (!r.player_accepts) setError(r.explanation || "Player rejected.");
    } catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur flex items-center justify-center p-4 z-50" onClick={onClose}>
      <div className="bg-zinc-900 border border-orange-500/40 rounded-xl p-6 w-full max-w-md" onClick={e => e.stopPropagation()}>
        <h2 className="text-xl font-semibold mb-1">Re-sign {fa.name}</h2>
        <div className="text-sm text-zinc-400 mb-1">
          OVR {fa.overall ?? "—"} · Age {fa.age ?? "—"} · {fa.years_of_service}yr vet · {fa.fa_type} · {fa.position ?? "—"}
        </div>
        <div className="text-xs text-zinc-400 mb-4 space-y-0.5">
          <div>Market value: <span className="font-bold text-orange-300">{fmt$(fa.market_value)}/yr</span></div>
          <div>Min CBA salary for {fa.years_of_service}-yr vet: <span className="font-mono">{fmt$(fa.min_salary)}</span></div>
          <div>Current cap hold: <span className="font-mono text-yellow-300">{fmt$(fa.hold_amount)}</span> (replaced when you sign)</div>
        </div>
        <div className="grid grid-cols-2 gap-3 mb-4">
          <div>
            <label className="block text-xs text-zinc-500 mb-1">Y1 Salary ($M)</label>
            <input type="number" step="0.1" value={salaryM} onChange={e => setSalaryM(parseFloat(e.target.value) || 0)} className="bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-sm w-full" />
          </div>
          <div>
            <label className="block text-xs text-zinc-500 mb-1">Years (Bird allows up to 5)</label>
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
