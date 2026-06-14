"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, fmt$, type TeamExceptions } from "@/lib/api";

/**
 * Shows which signing/trade tools the team has available right now:
 *   - Cap space (or "over the cap")
 *   - MLE variant (room, non-tax, taxpayer, or blocked)
 *   - Bi-Annual exception
 *   - Minimum exception
 *   - Bird-eligible own free agents
 *   - Live Traded Player Exceptions (TPEs)
 *
 * Used on the Free Agents page and (with showTPEs only) on the Trade page.
 */
export function TeamExceptionsPanel({
  tricode,
  season,
  variant = "full",
}: {
  tricode: string;
  season?: string;
  variant?: "full" | "tpe-only";
}) {
  const [data, setData] = useState<TeamExceptions | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!tricode) return;
    api.teamExceptions(tricode, season).then(setData).catch(e => setErr(String(e)));
  }, [tricode, season]);

  if (err) return <div className="text-xs text-red-300">Failed to load exceptions: {err}</div>;
  if (!data) return null;

  if (variant === "tpe-only") {
    if (data.trade_exceptions.length === 0) {
      return (
        <div className="text-xs text-zinc-500">
          {tricode} has no live Traded Player Exceptions.
        </div>
      );
    }
    return (
      <div className="text-xs space-y-1">
        <div className="uppercase tracking-wider text-zinc-500">{tricode} Trade Exceptions (TPEs)</div>
        {data.trade_exceptions.map(t => (
          <div key={t.id} className="flex items-center justify-between bg-zinc-900 border border-zinc-800 rounded px-2 py-1">
            <span className="text-zinc-300">
              {t.source ? `from ${t.source}` : "from trade"} · expires {t.expires}
            </span>
            <span className="font-mono font-bold text-emerald-300">{fmt$(t.remaining)}</span>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 mb-6">
      <div className="flex items-baseline justify-between mb-3">
        <div>
          <div className="text-xs uppercase tracking-wider text-zinc-500">Available Signing Tools</div>
          <div className="text-sm text-zinc-300">
            What <span className="font-mono font-bold text-orange-300">{tricode}</span> can use this offseason
          </div>
        </div>
        <Link
          href={`/team/${tricode}`}
          className="text-xs text-zinc-500 hover:text-orange-400"
        >
          View full cap →
        </Link>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        {/* Cap space card */}
        <ExceptionCard
          label={data.is_over_cap ? "Cap Space" : "Cap Space"}
          amount={data.is_over_cap ? 0 : data.cap_space}
          available={!data.is_over_cap}
          note={
            data.is_above_second_apron
              ? "Above the 2nd apron — heavily restricted."
              : data.is_above_first_apron
              ? "Above the 1st apron."
              : data.is_over_cap
              ? "Over the cap — must use exceptions."
              : "Under the cap. Sign for any amount up to cap."
          }
        />
        <ExceptionCard
          label={data.mle.label}
          amount={data.mle.amount}
          available={data.mle.available}
          note={data.mle.note}
        />
        <ExceptionCard
          label={data.bae.label}
          amount={data.bae.amount}
          available={data.bae.available}
          note={data.bae.note}
        />
        <ExceptionCard
          label={data.minimum.label}
          amount={data.minimum.amount}
          available
          note={data.minimum.note}
        />
      </div>

      {data.bird_eligible.length > 0 && (
        <div className="mt-4 pt-3 border-t border-zinc-800">
          <div className="text-xs uppercase tracking-wider text-zinc-500 mb-2">
            Bird Rights — your own free agents ({data.bird_eligible.length})
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-1.5 text-xs">
            {data.bird_eligible.map(p => (
              <div key={p.player_id} className="bg-zinc-950 border border-emerald-700/30 rounded px-2 py-1 flex items-center justify-between">
                <span className="text-zinc-200">{p.name}</span>
                <span className="text-zinc-500 font-mono">OVR {p.overall ?? "—"}</span>
              </div>
            ))}
          </div>
          <div className="text-[11px] text-zinc-600 mt-1.5">
            Re-sign any of these over the cap regardless of payroll. Renounce on your team page to clear the hold.
          </div>
        </div>
      )}

      {data.trade_exceptions.length > 0 && (
        <div className="mt-4 pt-3 border-t border-zinc-800">
          <div className="text-xs uppercase tracking-wider text-zinc-500 mb-2">
            Trade Exceptions (TPEs) — usable to absorb salary in a trade
          </div>
          <div className="space-y-1 text-xs">
            {data.trade_exceptions.map(t => (
              <div key={t.id} className="flex items-center justify-between bg-zinc-950 border border-emerald-700/30 rounded px-2 py-1">
                <span className="text-zinc-300">
                  {t.source ? `from ${t.source}` : "from trade"} · expires {t.expires}
                </span>
                <span className="font-mono font-bold text-emerald-300">{fmt$(t.remaining)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ExceptionCard({ label, amount, available, note }: {
  label: string;
  amount: number;
  available: boolean;
  note: string;
}) {
  return (
    <div className={`rounded-lg p-3 border ${
      available
        ? "border-emerald-700/40 bg-emerald-900/10"
        : "border-zinc-800 bg-zinc-950 opacity-60"
    }`}>
      <div className="text-[10px] uppercase tracking-wider text-zinc-500">{label}</div>
      <div className={`font-mono text-lg font-bold mt-0.5 ${available ? "text-emerald-300" : "text-zinc-500"}`}>
        {available ? fmt$(amount) : "—"}
      </div>
      <div className="text-[11px] text-zinc-500 mt-1 leading-snug">{note}</div>
    </div>
  );
}
