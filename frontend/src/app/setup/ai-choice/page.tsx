"use client";

import { useRouter } from "next/navigation";
import { BackButton } from "@/app/back-button";

const KEY = "nba_gm_ai_veto_disabled";

export default function AiChoicePage() {
  const router = useRouter();

  const pick = (aiOn: boolean) => {
    if (typeof window !== "undefined") {
      localStorage.setItem(KEY, aiOn ? "false" : "true");
    }
    router.push("/setup/team?mode=career");
  };

  return (
    <div className="max-w-3xl mx-auto px-6 py-16">
      <BackButton />
      <h1 className="text-3xl font-bold tracking-tight mt-2">How should other teams behave?</h1>
      <p className="text-zinc-400 mt-2 mb-10">
        Full GM Mode lets you make trades, sign free agents, and run drafts. The other 29 teams can either
        evaluate your moves like real GMs would, or just say yes to anything that&apos;s legal under the CBA.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        <button
          onClick={() => pick(true)}
          className="text-left rounded-2xl border-2 border-orange-500/60 hover:border-orange-400 bg-gradient-to-br from-orange-900/30 to-zinc-950 p-6 transition group"
        >
          <div className="text-xs uppercase tracking-wider text-orange-400 mb-2">Realistic</div>
          <h2 className="text-2xl font-bold mb-2">AI On <span className="text-zinc-500 text-base font-normal">(Recommended)</span></h2>
          <ul className="text-sm text-zinc-300 space-y-1.5 mb-4">
            <li>· Opposing teams evaluate your trade offers and can reject lowballs</li>
            <li>· Free agents demand fair-market salaries (no Jokic-for-min)</li>
            <li>· Trades involving picks are scrutinized more (no #1 for #12)</li>
            <li>· The simulation feels like a real NBA front-office</li>
          </ul>
          <div className="text-sm text-orange-400 font-medium group-hover:underline">Start with AI On →</div>
        </button>
        <button
          onClick={() => pick(false)}
          className="text-left rounded-2xl border-2 border-zinc-700 hover:border-zinc-500 bg-gradient-to-br from-zinc-900 to-zinc-950 p-6 transition group"
        >
          <div className="text-xs uppercase tracking-wider text-zinc-500 mb-2">Sandbox</div>
          <h2 className="text-2xl font-bold mb-2">AI Off</h2>
          <ul className="text-sm text-zinc-300 space-y-1.5 mb-4">
            <li>· Any CBA-legal trade goes through, regardless of value</li>
            <li>· Free agents accept any salary above the league minimum</li>
            <li>· Still sims seasons, tracks awards, and persists state</li>
            <li>· Good for experimentation while still playing through the years</li>
          </ul>
          <div className="text-sm text-zinc-300 font-medium group-hover:underline">Start with AI Off →</div>
        </button>
      </div>

      <p className="text-xs text-zinc-600 mt-6">
        You can toggle this any time during the game from the &quot;AI Off&quot; checkbox in the top-right nav.
      </p>
    </div>
  );
}
