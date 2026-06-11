import Link from "next/link";

export default function Home() {
  return (
    <div className="max-w-4xl mx-auto px-6 py-16">
      <div className="mb-10">
        <h1 className="text-4xl font-bold tracking-tight">NBA GM <span className="text-orange-400">2026</span></h1>
        <p className="text-zinc-400 mt-2">Pick your mode. June 2026 — Finals wrapping up. Free agency opens July 1.</p>
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
            Sandbox tool for exploring offseason moves. Trade, sign FAs, run the draft for your team.
            <span className="text-emerald-300 block mt-1">Resets to fresh state every time you enter — doesn&apos;t affect your Full GM save.</span>
          </p>
          <div className="text-sm text-emerald-400 font-medium group-hover:underline">Choose your team →</div>
        </Link>
        <Link
          href="/setup/ai-choice"
          className="group rounded-2xl border border-zinc-800 hover:border-orange-500/60 bg-gradient-to-br from-zinc-900 to-zinc-950 p-6 transition"
        >
          <div className="flex items-center gap-2 mb-3">
            <span className="text-xs px-2 py-0.5 rounded bg-orange-900/40 text-orange-300 font-medium uppercase tracking-wider">Mode 2</span>
          </div>
          <h2 className="text-2xl font-bold mb-2">Full GM Mode</h2>
          <p className="text-sm text-zinc-400 mb-4">
            Build a real career across multiple seasons. Sim 2026-27 → run 2027-28 offseason → sim 2027-28.
            <span className="text-orange-300 block mt-1">Your moves persist. Auto-saved after each sim and rollover.</span>
          </p>
          <div className="text-sm text-orange-400 font-medium group-hover:underline">Choose AI behavior →</div>
        </Link>
      </div>
    </div>
  );
}
