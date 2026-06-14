import Link from "next/link";
import { HomeResetButton } from "./home-reset-button";

export default function Home() {
  return (
    <div className="max-w-4xl mx-auto px-6 py-16">
      <div className="flex items-start justify-between gap-4 mb-10">
        <div>
          <h1 className="text-4xl font-bold tracking-tight">NBA GM <span className="text-orange-400">2026</span></h1>
          <p className="text-zinc-400 mt-2">It&apos;s June 2026. The Finals are wrapping up and free agency opens July 1. Pick a mode.</p>
        </div>
        <HomeResetButton />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        <Link
          href="/setup/team?mode=offseason"
          className="group rounded-2xl border border-zinc-800 hover:border-emerald-500/60 bg-gradient-to-br from-zinc-900 to-zinc-950 p-6 transition"
        >
          <div className="flex items-center gap-2 mb-3">
            <span className="text-xs px-2 py-0.5 rounded bg-emerald-900/40 text-emerald-300 font-medium uppercase tracking-wider">Sandbox</span>
          </div>
          <h2 className="text-2xl font-bold mb-2">2026 Offseason Mode</h2>
          <p className="text-sm text-zinc-400 mb-4">
            A sandbox for the 2026 offseason. Make trades, sign free agents, run the draft for any team — no simulation,
            no consequences.
          </p>
          <ul className="text-xs text-zinc-500 mb-4 space-y-0.5">
            <li>· Every action is CBA-validated against real cap rules</li>
            <li>· Resets to a fresh league every time you enter</li>
            <li>· Doesn&apos;t affect your Full GM save</li>
          </ul>
          <div className="text-sm text-emerald-400 font-medium group-hover:underline">Choose your team →</div>
        </Link>
        <Link
          href="/setup/ai-choice"
          className="group rounded-2xl border border-zinc-800 hover:border-orange-500/60 bg-gradient-to-br from-zinc-900 to-zinc-950 p-6 transition"
        >
          <div className="flex items-center gap-2 mb-3">
            <span className="text-xs px-2 py-0.5 rounded bg-orange-900/40 text-orange-300 font-medium uppercase tracking-wider">Career</span>
          </div>
          <h2 className="text-2xl font-bold mb-2">Full GM Mode</h2>
          <p className="text-sm text-zinc-400 mb-4">
            Pick one team and build a real career across multiple seasons. Run the offseason, sim the season,
            roll over to the next one, repeat.
          </p>
          <ul className="text-xs text-zinc-500 mb-4 space-y-0.5">
            <li>· AI evaluates your trade offers like real GMs would</li>
            <li>· Free agents reject lowball offers</li>
            <li>· Use the 💾 Save button in the nav to checkpoint progress</li>
          </ul>
          <div className="text-sm text-orange-400 font-medium group-hover:underline">Choose AI behavior →</div>
        </Link>
      </div>
    </div>
  );
}
