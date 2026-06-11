"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";

/**
 * Banner shown when arriving at the team page right after a season rollover.
 * Reads ?rollover=2027-28&dropped=X&new_fas=Y from the URL.
 */
export function RolloverBanner({ tricode }: { tricode: string }) {
  const sp = useSearchParams();
  const newSeason = sp.get("rollover");
  if (!newSeason) return null;
  const dropped = sp.get("dropped") ?? "0";
  const newFAs = sp.get("new_fas") ?? "0";
  const draftYear = newSeason.split("-")[0];

  return (
    <div className="rounded-xl border-2 border-emerald-500 bg-gradient-to-br from-emerald-900/30 to-zinc-900 p-5 mb-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-xs uppercase tracking-wider text-emerald-300 font-bold mb-1">Welcome to the {newSeason} Offseason</div>
          <p className="text-sm text-zinc-200 mb-2">
            Rolled over from the previous season: <span className="text-emerald-300 font-semibold">{dropped} contracts expired</span>,{" "}
            <span className="text-emerald-300 font-semibold">{newFAs} new free agents</span>. Players aged +1, young guys developed, vets declined.
          </p>
          <p className="text-sm text-zinc-300">
            Below is your current roster and cap. Use the GM Decisions panel + the phase nav to work through:
            <span className="text-orange-300 font-semibold"> Draft → Options → FA &amp; Trades → Sim</span>.
          </p>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2 mt-4 text-xs">
        <Link href={`/draft/${draftYear}/live`} className="px-3 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500 text-white font-medium">
          1. Go to Draft →
        </Link>
        <Link href="/options" className="px-3 py-1.5 rounded bg-zinc-800 hover:bg-zinc-700">2. Options</Link>
        <Link href="/free-agents" className="px-3 py-1.5 rounded bg-zinc-800 hover:bg-zinc-700">3. Free Agents</Link>
        <Link href="/trade" className="px-3 py-1.5 rounded bg-zinc-800 hover:bg-zinc-700">3. Trade</Link>
        <Link href="/sim" className="px-3 py-1.5 rounded bg-zinc-800 hover:bg-zinc-700">4. Sim Season</Link>
      </div>
      <p className="text-xs text-zinc-500 mt-3">
        Tip: do them in order. Sim is blocked until the draft is complete.
      </p>
    </div>
  );
}
