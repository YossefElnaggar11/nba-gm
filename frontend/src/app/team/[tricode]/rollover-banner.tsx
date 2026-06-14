"use client";

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

  return (
    <div className="rounded-xl border border-emerald-500/40 bg-emerald-900/10 px-4 py-3 mb-3 flex items-center justify-between gap-3">
      <div className="text-sm">
        <span className="text-emerald-300 font-bold">Welcome to the {newSeason} Offseason.</span>
        <span className="text-zinc-300 ml-1">
          {dropped} contracts expired, {newFAs} new free agents. The checklist below shows what&apos;s next.
        </span>
      </div>
    </div>
  );
}
