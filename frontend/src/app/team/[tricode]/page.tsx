import Link from "next/link";
import { api, fmt$Full, fmt$ } from "@/lib/api";
import { RenounceHoldButton } from "./renounce-button";
import { TeamDashboard } from "./team-dashboard";
import { SeasonStats } from "./season-stats";
import { TeamSeasonSummary } from "./team-season-summary";

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
    ? { text: "Above 2nd Apron — hard-capped, severe restrictions", color: "text-red-400" }
    : cap.over_first_apron
    ? { text: "Above 1st Apron — apron restrictions in effect", color: "text-orange-400" }
    : cap.over_tax
    ? { text: "Over Luxury Tax", color: "text-yellow-400" }
    : cap.cap_space < 0
    ? { text: "Over the cap (no cap room)", color: "text-zinc-400" }
    : { text: `${fmt$(cap.cap_space)} in cap space`, color: "text-emerald-400" };

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
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

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-5 text-sm">
            <Stat label="Total Salary" value={fmt$(cap.total_salary)} />
            <Stat label="Cap" value={fmt$(cap.cap_levels.salary_cap)} />
            <Stat label="Luxury Tax" value={fmt$(cap.cap_levels.luxury_tax)} highlight={cap.over_tax} />
            <Stat label="1st Apron" value={fmt$(cap.cap_levels.first_apron)} highlight={cap.over_first_apron} />
          </div>

          <div className={`mb-4 text-sm font-medium ${apronStatus.color}`}>{apronStatus.text}</div>

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
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
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
    </div>
  );
}

function Stat({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className={`rounded-md p-3 border ${highlight ? "border-orange-500/50 bg-orange-500/5" : "border-zinc-800 bg-zinc-950"}`}>
      <div className="text-xs uppercase tracking-wider text-zinc-500">{label}</div>
      <div className="font-semibold mt-1">{value}</div>
    </div>
  );
}
