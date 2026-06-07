"use client";

import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useUserContext } from "@/lib/user-context";

export function NavUserBadge() {
  const { team, mode, ready } = useUserContext();
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  const reset = async () => {
    if (!confirm("Reset the entire game to the 2026-27 offseason starting state? All trades, signings, draft picks, and sim results will be wiped.")) return;
    setBusy(true);
    try {
      await api.reset();
      router.refresh();
    } finally { setBusy(false); }
  };

  if (!ready) return null;
  if (!team) {
    return (
      <div className="ml-auto flex items-center gap-3 text-xs">
        <button onClick={reset} disabled={busy} className="px-2 py-0.5 rounded border border-zinc-700 hover:bg-zinc-800 disabled:opacity-50">
          {busy ? "Resetting…" : "↻ Reset"}
        </button>
        <Link href="/" className="text-zinc-500 hover:text-zinc-300">Pick a team →</Link>
      </div>
    );
  }
  return (
    <div className="ml-auto flex items-center gap-3 text-xs">
      <span className={`px-2 py-0.5 rounded ${mode === "career" ? "bg-orange-900/40 text-orange-300" : "bg-emerald-900/40 text-emerald-300"} font-medium uppercase tracking-wider`}>
        {mode === "career" ? "Full GM" : "Offseason"}
      </span>
      <Link href={`/team/${team}`} className="text-zinc-300 hover:text-white">
        Your team: <span className="font-bold">{team}</span>
      </Link>
      <Link href="/" className="text-zinc-500 hover:text-zinc-300">Change</Link>
      <button onClick={reset} disabled={busy} className="px-2 py-0.5 rounded border border-zinc-700 hover:bg-zinc-800 disabled:opacity-50">
        {busy ? "Resetting…" : "↻ Reset"}
      </button>
    </div>
  );
}

export function NavQuickLinks() {
  const { team, mode } = useUserContext();
  return (
    <div className="flex items-center gap-4 text-sm text-zinc-300">
      <Link href="/" className="hover:text-white transition">Home</Link>
      {team && <Link href={`/team/${team}`} className="hover:text-white transition">My Team</Link>}
      <Link href="/options" className="hover:text-white transition">Options</Link>
      <Link href="/trade" className="hover:text-white transition">Trade</Link>
      <Link href="/free-agents" className="hover:text-white transition">FAs</Link>
      <Link href="/draft/2026/live" className="hover:text-white transition text-emerald-400">▶ Live Draft</Link>
      {mode === "career" && (
        <>
          <Link href="/sim" className="hover:text-white transition text-orange-400">▶ Sim Season</Link>
          <Link href="/awards" className="hover:text-white transition">Awards</Link>
          <Link href="/leaders" className="hover:text-white transition">Leaders</Link>
        </>
      )}
    </div>
  );
}
