import Link from "next/link";
import { ResetButton } from "./reset-button";

export default function Home() {
  return (
    <div className="max-w-4xl mx-auto px-6 py-16">
      <div className="flex items-center justify-between mb-10">
        <div>
          <h1 className="text-4xl font-bold tracking-tight">Pick your mode</h1>
          <p className="text-zinc-400 mt-2">June 7, 2026. Finals wrapping up. Free agency opens July 1.</p>
        </div>
        <ResetButton />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        <Link
          href="/setup/team?mode=offseason"
          className="group rounded-2xl border border-zinc-800 hover:border-emerald-500/60 bg-gradient-to-br from-zinc-900 to-zinc-950 p-6 transition"
        >
          <div className="flex items-center gap-2 mb-3">
            <span className="text-xs px-2 py-0.5 rounded bg-emerald-900/40 text-emerald-300 font-medium uppercase tracking-wider">Mode 1</span>
          </div>
          <h2 className="text-2xl font-bold mb-2">2026 Offseason Mode</h2>
          <p className="text-sm text-zinc-400 mb-4">
            Make moves for your favorite team going into the 2026-27 season.
          </p>
          <div className="text-sm text-emerald-400 font-medium group-hover:underline">Choose your team →</div>
        </Link>
        <Link
          href="/setup/team?mode=career"
          className="group rounded-2xl border border-zinc-800 hover:border-orange-500/60 bg-gradient-to-br from-zinc-900 to-zinc-950 p-6 transition"
        >
          <div className="flex items-center gap-2 mb-3">
            <span className="text-xs px-2 py-0.5 rounded bg-orange-900/40 text-orange-300 font-medium uppercase tracking-wider">Mode 2</span>
          </div>
          <h2 className="text-2xl font-bold mb-2">Full GM Mode</h2>
          <p className="text-sm text-zinc-400 mb-4">
            See how your moves impact the team across the next few seasons. Sim, then run the next offseason. Repeat.
          </p>
          <div className="text-sm text-orange-400 font-medium group-hover:underline">Choose your team →</div>
        </Link>
      </div>
    </div>
  );
}
