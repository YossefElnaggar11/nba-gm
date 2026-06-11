import Link from "next/link";
import { api, fmt$Full, fmt$ } from "@/lib/api";
import { RenounceHoldButton } from "./renounce-button";
import { TeamDashboard } from "./team-dashboard";
import { SeasonStats } from "./season-stats";
import { TeamSeasonSummary } from "./team-season-summary";
import { OwnFreeAgents } from "./own-fas";
import { LastSeasonStats } from "./last-season-stats";
import { RolloverBanner } from "./rollover-banner";
import { BackButton } from "@/app/back-button";

export const dynamic = "force-dynamic";

export default async function TeamPage({ params }: { params: Promise<{ tricode: string }> }) {
  const { tricode } = await params;
  const code = tricode.toUpperCase();
  const [team, roster, cap, arsenal] = await Promise.all([
    api.team(code),
    api.roster(code),
    api.capSheet(code),
    api.teamArsenal(code),
  ]);

  const apronStatus = cap.over_second_apron
    ? { tier: "SECOND APRON", text: "Hard-capped at 2nd apron · No aggregation · No taxpayer MLE · No BAE · Pick 7 yrs out frozen", color: "red", border: "border-red-500", bg: "bg-red-900/20" }
    : cap.over_first_apron
    ? { tier: "FIRST APRON", text: "Apron restrictions in effect · Hard-capped if using non-tax MLE / BAE / S&T-receive", color: "orange", border: "border-orange-500", bg: "bg-orange-900/20" }
    : cap.over_tax
    ? { tier: "OVER LUXURY TAX", text: "Paying tax penalties · Can still use taxpayer MLE", color: "yellow", border: "border-yellow-500", bg: "bg-yellow-900/20" }
    : cap.cap_space < 0
    ? { tier: "OVER CAP", text: "Above the salary cap but under tax · Full non-tax MLE available", color: "zinc", border: "border-zinc-700", bg: "bg-zinc-800/40" }
    : { tier: "UNDER CAP", text: `${fmt$(cap.cap_space)} of cap space available`, color: "emerald", border: "border-emerald-500", bg: "bg-emerald-900/20" };

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      <BackButton />

      <RolloverBanner tricode={code} />

      <div
        className="rounded-xl p-6 mb-6 flex items-center justify-between"
        style={{ background: `linear-gradient(90deg, ${team.primary_color}, ${team.secondary_color})` }}
      >
        <div className="flex items-center gap-5">
          {team.logo_url && (
            <img src={team.logo_url} alt={team.full_name} className="w-20 h-20 object-contain drop-shadow-lg" />
          )}
          <div>
            <div className="text-xs text-white/80 tracking-wider uppercase">
              {team.conference} · {team.division}
            </div>
            <h1 className="text-4xl font-bold tracking-tight text-white drop-shadow">
              {team.full_name}
            </h1>
          </div>
        </div>
        <div className="text-right">
          <div className="text-5xl font-black text-white/90 drop-shadow">{team.tricode}</div>
          <div className="mt-1 text-xs text-white/80">2026-27 Season</div>
        </div>
      </div>

      <TeamDashboard viewTricode={code} />

      <TeamSeasonSummary tricode={code} />

      <OwnFreeAgents tricode={code} />

      <SeasonStats tricode={code} />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Cap sheet */}
        <div className="lg:col-span-2 bg-zinc-900 border border-zinc-800 rounded-lg p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold">2026-27 Roster &amp; Cap</h2>
            <Link
              href={`/trade?team=${team.tricode}`}
              className="text-xs px-3 py-1.5 rounded-md bg-orange-500 hover:bg-orange-400 text-black font-medium"
            >
              Propose a Trade →
            </Link>
          </div>

          {/* Apron Status Banner — clearly shows which tier the team is in */}
          <div className={`rounded-lg border-2 ${apronStatus.border} ${apronStatus.bg} p-3 mb-4`}>
            <div className="flex items-center justify-between">
              <div>
                <div className={`text-xs uppercase tracking-wider font-bold text-${apronStatus.color}-400`}>
                  {apronStatus.tier}
                </div>
                <div className="text-sm text-zinc-300 mt-0.5">{apronStatus.text}</div>
              </div>
              <div className="text-right">
                <div className="text-xs text-zinc-500">Payroll</div>
                <div className="font-mono font-bold text-lg">{fmt$(cap.total_salary)}</div>
              </div>
            </div>
          </div>

          {/* All 5 cap tiers shown side-by-side with payroll progression */}
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 mb-5 text-xs">
            <CapTier label="Cap" value={cap.cap_levels.salary_cap} payroll={cap.total_salary} />
            <CapTier label="Luxury Tax" value={cap.cap_levels.luxury_tax} payroll={cap.total_salary} crossed={cap.over_tax} accent="yellow" />
            <CapTier label="1st Apron" value={cap.cap_levels.first_apron} payroll={cap.total_salary} crossed={cap.over_first_apron} accent="orange" />
            <CapTier label="2nd Apron" value={cap.cap_levels.second_apron} payroll={cap.total_salary} crossed={cap.over_second_apron} accent="red" />
            <CapTier label="Cap Space" value={cap.cap_space} payroll={0} accent="emerald" isSpace />
          </div>

          <table className="w-full text-sm">
            <thead className="text-xs uppercase tracking-wider text-zinc-500 border-b border-zinc-800">
              <tr>
                <th className="text-left pb-2">Player</th>
                <th className="text-right pb-2 w-20">Age</th>
                <th className="text-right pb-2 w-32">2026-27</th>
                <th className="text-right pb-2 w-24">Type</th>
              </tr>
            </thead>
            <tbody>
              {cap.players.map((p) => (
                <tr key={p.player_id} className="border-b border-zinc-800/50 hover:bg-zinc-800/30">
                  <td className="py-2">{p.name}</td>
                  <td className="text-right text-zinc-400">{p.age ?? "—"}</td>
                  <td className="text-right font-mono">{fmt$Full(p.salary)}</td>
                  <td className="text-right">
                    {p.option_type === "PLAYER" && (
                      <span className="text-xs px-1.5 py-0.5 rounded bg-yellow-900/40 text-yellow-400">P-OPT</span>
                    )}
                    {p.option_type === "TEAM" && (
                      <span className="text-xs px-1.5 py-0.5 rounded bg-blue-900/40 text-blue-400">T-OPT</span>
                    )}
                    {!p.guaranteed && (
                      <span className="text-xs ml-1 px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400">non-gtd</span>
                    )}
                  </td>
                </tr>
              ))}
              <tr className="font-semibold">
                <td className="pt-3 text-right" colSpan={2}>Total ({cap.players.length} players)</td>
                <td className="pt-3 text-right font-mono">{fmt$Full(cap.total_salary)}</td>
                <td />
              </tr>
            </tbody>
          </table>

          {roster.count > cap.players.length && (
            <div className="text-xs text-zinc-500 mt-3">
              {roster.count - cap.players.length} additional players on roster without 2026-27 contracts
              (option pending / two-way / unsigned).
            </div>
          )}

          {cap.cap_holds.length > 0 && (
            <div className="mt-6 pt-4 border-t border-zinc-800">
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-sm uppercase tracking-wider text-zinc-500">
                  Cap Holds ({cap.cap_holds.length} · {fmt$(cap.cap_holds_total)})
                </h3>
                <span className="text-xs text-zinc-600">Bird-rights placeholders for expiring own players. Renounce to free up cap room (loses Bird rights).</span>
              </div>
              <table className="w-full text-sm">
                <tbody>
                  {cap.cap_holds.map((h) => (
                    <tr key={h.hold_id} className="border-b border-zinc-800/30 hover:bg-zinc-800/20">
                      <td className="py-1.5 text-zinc-300">{h.name}</td>
                      <td className="py-1.5 text-right text-zinc-400 w-16">{h.age ?? "—"}</td>
                      <td className="py-1.5 text-right font-mono text-zinc-300 w-32">{fmt$Full(h.amount)}</td>
                      <td className="py-1.5 text-right w-24">
                        <RenounceHoldButton holdId={h.hold_id} />
                      </td>
                    </tr>
                  ))}
                  <tr className="font-semibold">
                    <td className="pt-2 text-right" colSpan={2}>Holds Total</td>
                    <td className="pt-2 text-right font-mono">{fmt$Full(cap.cap_holds_total)}</td>
                    <td />
                  </tr>
                  <tr className="font-semibold border-t border-zinc-800">
                    <td className="pt-2 text-right" colSpan={2}>Effective Payroll</td>
                    <td className="pt-2 text-right font-mono text-orange-400">{fmt$Full(cap.total_salary)}</td>
                    <td />
                  </tr>
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Pick arsenal */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 lg:row-start-1 lg:col-start-3">
          <h2 className="text-lg font-semibold mb-4">Draft Arsenal</h2>
          <div className="space-y-3 text-sm">
            {Array.from(new Set(arsenal.picks.map((p) => p.year)))
              .sort()
              .map((year) => (
                <div key={year}>
                  <div className="text-xs uppercase tracking-wider text-zinc-500 mb-1">{year}</div>
                  <div className="space-y-1">
                    {arsenal.picks
                      .filter((p) => p.year === year)
                      .map((p, i) => (
                        <div key={i} className="flex items-center gap-2">
                          <span className={`text-xs px-1.5 py-0.5 rounded font-mono ${
                            p.round === 1 ? "bg-emerald-900/40 text-emerald-300" : "bg-zinc-800 text-zinc-400"
                          }`}>
                            R{p.round}
                          </span>
                          <span className="text-sm">
                            {p.original === team.tricode ? "Own pick" : `from ${p.original}`}
                            {p.pick_number ? ` (#${p.pick_number})` : ""}
                          </span>
                          {p.is_swap && (
                            <span className="text-xs px-1.5 py-0.5 rounded bg-purple-900/40 text-purple-300">SWAP</span>
                          )}
                          {p.protection && (
                            <span className="text-xs text-zinc-500">· {p.protection}</span>
                          )}
                        </div>
                      ))}
                  </div>
                </div>
              ))}
          </div>
        </div>
      </div>

      <LastSeasonStats tricode={code} />
    </div>
  );
}

function CapTier({ label, value, payroll, crossed, accent, isSpace }: {
  label: string;
  value: number;
  payroll: number;
  crossed?: boolean;
  accent?: string;
  isSpace?: boolean;
}) {
  const colorMap: Record<string, string> = {
    yellow: "border-yellow-500/60 text-yellow-300",
    orange: "border-orange-500/70 text-orange-300",
    red: "border-red-500/70 text-red-300",
    emerald: "border-emerald-500/60 text-emerald-300",
  };
  const baseStyle = crossed && accent
    ? `${colorMap[accent]} bg-${accent}-900/10 ring-1 ring-${accent}-500/40`
    : "border-zinc-800 bg-zinc-950 text-zinc-400";
  return (
    <div className={`rounded-md p-2.5 border ${baseStyle}`}>
      <div className="text-[10px] uppercase tracking-wider text-zinc-500">{label}</div>
      <div className={`font-semibold mt-0.5 font-mono ${crossed ? "" : ""}`}>
        {value < 0 ? `-${fmt$(Math.abs(value))}` : fmt$(value)}
      </div>
      {!isSpace && (
        <div className="text-[10px] text-zinc-600 mt-0.5">
          {crossed ? "OVER" : `${fmt$(Math.max(0, value - payroll))} below`}
        </div>
      )}
    </div>
  );
}
