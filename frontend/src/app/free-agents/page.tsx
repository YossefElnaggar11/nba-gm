"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, fmt$, type FreeAgent, type Team } from "@/lib/api";
import { useUserContext } from "@/lib/user-context";
import { useAiVetoDisabled } from "@/lib/ai-veto";
import { useNextOffseasonStep } from "@/lib/use-next-step";
import { BackButton } from "@/app/back-button";
import { TeamExceptionsPanel } from "@/app/team-exceptions-panel";

export default function FreeAgentsPage() {
  const router = useRouter();
  const { team: userTeam, mode } = useUserContext();
  const [aiDisabled] = useAiVetoDisabled();
  const [fas, setFas] = useState<FreeAgent[]>([]);
  const [teams, setTeams] = useState<Team[]>([]);
  const [signing, setSigning] = useState<FreeAgent | null>(null);
  const [signTeam, setSignTeam] = useState<string>("LAL");
  const [salaryM, setSalaryM] = useState<number>(2.5);
  const [years, setYears] = useState<number>(1);
  const [using, setUsing] = useState<string>("MIN");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [working, setWorking] = useState(false);

  const [currentSeason, setCurrentSeason] = useState("2026-27");
  const next = useNextOffseasonStep("fa");
  const load = async () => {
    const [a, b, s] = await Promise.all([api.freeAgents(), api.teams(), api.state()]);
    setFas(a);
    setTeams(b);
    setCurrentSeason(s.current_season);
  };

  useEffect(() => {
    document.title = `Free Agents · NBA GM 2026`;
  }, []);
  useEffect(() => { load(); }, []);
  useEffect(() => {
    if (userTeam) setSignTeam(userTeam);
  }, [userTeam]);

  const openSign = (fa: FreeAgent) => {
    setError(null);
    setInfo(null);
    setSigning(fa);
    // Default to MIN legal salary — user can negotiate up from there.
    const startingOffer = fa.min_salary_for_yos / 1_000_000;
    setSalaryM(Math.round(startingOffer * 100) / 100);
    setUsing("MIN");
  };

  // Auto-suggest the right exception based on the salary the user types.
  // Keeps the user from accidentally over-paying via the "MIN" mechanism.
  useEffect(() => {
    if (!signing) return;
    const salary = salaryM * 1_000_000;
    const minSal = signing.min_salary_for_yos;
    if (salary <= minSal * 1.02) {
      setUsing("MIN");
    } else if (signing.prior_team === signTeam) {
      // Own free agent — use Bird rights so it goes over the cap legally.
      setUsing("BIRD");
    } else if (salary <= 14_000_000) {
      // Mid-level deal — non-tax MLE is the typical mechanism.
      setUsing("MLE_NON_TAX");
    } else {
      // Big outside signing — needs cap space.
      setUsing("NON_BIRD");
    }
  }, [salaryM, signing, signTeam]);

  const ufa = fas.filter((f) => f.fa_type === "UFA");
  const rfa = fas.filter((f) => f.fa_type === "RFA");
  const others = fas.filter((f) => f.fa_type !== "UFA" && f.fa_type !== "RFA");

  const submit = async (apply: boolean) => {
    if (!signing) return;
    setError(null);
    setInfo(null);
    setWorking(true);
    try {
      const r = await api.signPlayer({
        player_id: signing.id,
        team: signTeam,
        first_season: currentSeason,
        salary_year1: Math.round(salaryM * 1_000_000),
        years,
        using,
        apply,
        career_mode: mode === "career" && !aiDisabled,
      });
      if (apply && r.applied) {
        setSigning(null);
        await load();
        router.refresh();
      } else if (!r.valid) {
        setError(r.violations.map(v => `[${v.severity}] ${v.message}`).join("\n"));
      } else if (!r.player_accepts) {
        setError(r.explanation || "Player rejected the offer.");
      } else {
        setInfo("✓ Signing is legal under the CBA — click Sign to execute.");
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setWorking(false);
    }
  };

  return (
    <div className="max-w-6xl mx-auto px-6 py-8">
      <BackButton />
      <div className="flex items-start justify-between mb-2 gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{currentSeason.split("-")[0]} Free Agent Market</h1>
          <p className="text-zinc-400 mt-1">
            {fas.length} players hit the market. FA opens July 1, {currentSeason.split("-")[0]}.
            {mode === "career" && <span className="ml-2 text-orange-400">· Lowball offers will be rejected.</span>}
          </p>
        </div>
        <Link href={next.href} className="shrink-0 px-4 py-2 rounded-md bg-orange-500 hover:bg-orange-400 text-black font-semibold text-sm whitespace-nowrap">
          {next.label}
        </Link>
      </div>

      {userTeam && <TeamExceptionsPanel tricode={userTeam} season={currentSeason} variant="full" />}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <Stat label="Unrestricted" value={ufa.length} color="emerald" />
        <Stat label="Restricted" value={rfa.length} color="yellow" />
        <Stat label="Two-Way / Other" value={others.length} color="zinc" />
      </div>

      <Section title="Unrestricted Free Agents" players={ufa} onSign={openSign} />
      <Section title="Restricted Free Agents" players={rfa} onSign={openSign} />
      <Section title="Two-Way / Other" players={others} onSign={openSign} />

      {signing && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur flex items-center justify-center p-4 z-50" onClick={() => setSigning(null)}>
          <div className="bg-zinc-900 border border-zinc-700 rounded-xl p-6 w-full max-w-md" onClick={e => e.stopPropagation()}>
            <h2 className="text-xl font-semibold mb-1">Sign {signing.name}</h2>
            <div className="text-sm text-zinc-400 mb-1">
              {signing.position ?? "—"} · Age {signing.age ?? "—"} · OVR {signing.overall ?? "—"} · {signing.fa_type}
            </div>
            <div className="text-sm text-orange-300 mb-4">
              Market value: ~<span className="font-bold">{fmt$(signing.market_value)}</span>/yr
              <span className="text-zinc-500"> · floor: {fmt$(Math.round(signing.market_value * 0.75))}/yr</span>
            </div>

            <div className="grid grid-cols-2 gap-3 mb-4">
              <Field label="Team">
                <select value={signTeam} onChange={e => setSignTeam(e.target.value)} className="bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-sm w-full">
                  {teams.map(t => <option key={t.tricode} value={t.tricode}>{t.tricode}</option>)}
                </select>
              </Field>
              <Field label="Mechanism">
                <select value={using} onChange={e => setUsing(e.target.value)} className="bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-sm w-full">
                  <option value="MIN">Minimum</option>
                  <option value="MLE_NON_TAX">Non-Tax MLE</option>
                  <option value="MLE_TAX">Taxpayer MLE</option>
                  <option value="MLE_ROOM">Room MLE</option>
                  <option value="BAE">Bi-Annual</option>
                  <option value="NON_BIRD">Cap Space</option>
                  <option value="BIRD">Bird Rights (own)</option>
                  <option value="MAX_BIRD">Max Bird</option>
                  <option value="MAX_NON_BIRD">Max Outside</option>
                </select>
              </Field>
              <Field label="Y1 Salary ($M)">
                <input type="number" step="0.1" value={salaryM} onChange={e => setSalaryM(parseFloat(e.target.value) || 0)} className="bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-sm w-full" />
              </Field>
              <Field label="Years">
                <input type="number" min={1} max={5} value={years} onChange={e => setYears(parseInt(e.target.value) || 1)} className="bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-sm w-full" />
              </Field>
            </div>

            {error && <div className="text-xs p-2 rounded bg-red-900/20 text-red-300 mb-3 whitespace-pre-line">{error}</div>}
            {info && <div className="text-xs p-2 rounded bg-emerald-900/20 text-emerald-300 mb-3">{info}</div>}

            <div className="flex gap-2 justify-end">
              <button onClick={() => setSigning(null)} className="px-3 py-1.5 text-sm rounded bg-zinc-800 hover:bg-zinc-700">Cancel</button>
              <button disabled={working} onClick={() => submit(false)} className="px-3 py-1.5 text-sm rounded bg-zinc-700 hover:bg-zinc-600">Check</button>
              <button disabled={working} onClick={() => submit(true)} className="px-3 py-1.5 text-sm rounded bg-orange-500 hover:bg-orange-400 text-black font-medium">Sign</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-xs text-zinc-500 mb-1">{label}</label>
      {children}
    </div>
  );
}

function Stat({ label, value, color }: { label: string; value: number; color: string }) {
  const colorMap: Record<string, string> = {
    emerald: "border-emerald-500/50 text-emerald-400",
    yellow: "border-yellow-500/50 text-yellow-400",
    zinc: "border-zinc-700 text-zinc-300",
  };
  return (
    <div className={`bg-zinc-900 border ${colorMap[color]} rounded-lg p-4`}>
      <div className="text-xs uppercase tracking-wider text-zinc-500">{label}</div>
      <div className="text-3xl font-bold mt-1">{value}</div>
    </div>
  );
}

function Section({ title, players, onSign }: { title: string; players: FreeAgent[]; onSign: (p: FreeAgent) => void }) {
  if (!players.length) return null;
  return (
    <div className="mb-8">
      <h2 className="text-sm uppercase tracking-wider text-zinc-500 mb-3">{title}</h2>
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-zinc-800/50 text-xs uppercase tracking-wider text-zinc-500">
            <tr>
              <th className="text-left px-4 py-2">Player</th>
              <th className="text-right px-4 py-2 w-12">OVR</th>
              <th className="text-left px-4 py-2 w-16">Pos</th>
              <th className="text-right px-4 py-2 w-16">Age</th>
              <th className="text-left px-4 py-2 w-20">Prior</th>
              <th className="text-right px-4 py-2 w-28">Market ~$/yr</th>
              <th className="text-right px-4 py-2 w-20"></th>
            </tr>
          </thead>
          <tbody>
            {players.sort((a, b) => (b.overall ?? 0) - (a.overall ?? 0)).map((p) => (
              <tr key={p.id} className="border-t border-zinc-800/50 hover:bg-zinc-800/30">
                <td className="px-4 py-2 font-medium">{p.name}</td>
                <td className="px-4 py-2 text-right font-mono text-zinc-300">{p.overall ?? "—"}</td>
                <td className="px-4 py-2 text-zinc-400">{p.position ?? "—"}</td>
                <td className="px-4 py-2 text-right text-zinc-400">{p.age ?? "—"}</td>
                <td className="px-4 py-2 text-zinc-400">{p.prior_team ?? "—"}</td>
                <td className="px-4 py-2 text-right font-mono text-orange-300">{fmt$(p.market_value)}</td>
                <td className="px-4 py-2 text-right">
                  <button onClick={() => onSign(p)} className="px-2 py-1 text-xs rounded bg-orange-500 hover:bg-orange-400 text-black font-medium">
                    Sign
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
