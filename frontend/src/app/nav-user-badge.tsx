"use client";

import Link from "next/link";
import { useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useUserContext } from "@/lib/user-context";
import { useAiVetoDisabled } from "@/lib/ai-veto";

export function NavBar() {
  const pathname = usePathname();
  // Home page and setup flow are minimal — no nav bar
  if (pathname === "/" || pathname.startsWith("/setup")) return null;
  return (
    <header className="border-b border-zinc-800 bg-zinc-900/60 backdrop-blur sticky top-0 z-10">
      <nav className="max-w-7xl mx-auto px-6 py-3 flex items-center gap-6">
        <Link href="/" className="font-bold text-lg tracking-tight">
          NBA GM <span className="text-orange-400">2026</span>
        </Link>
        <NavQuickLinks />
        <NavUserBadge />
      </nav>
    </header>
  );
}

export function NavUserBadge() {
  const { team, mode, ready } = useUserContext();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [aiDisabled, setAiDisabled] = useAiVetoDisabled();

  const reset = async () => {
    setBusy(true);
    try {
      await api.reset();
      // Hard reload to clear all client state on the current page
      if (typeof window !== "undefined") window.location.reload();
    } finally { setBusy(false); }
  };

  const save = async () => {
    setBusy(true);
    try {
      const r = await api.saveCareer();
      if (r.ok) setSavedAt(Date.now());
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
      {mode === "career" && (
        <label className="flex items-center gap-1 cursor-pointer text-zinc-400 hover:text-zinc-200" title="When on, any CBA-legal trade/signing bypasses AI evaluation">
          <input type="checkbox" checked={aiDisabled} onChange={e => setAiDisabled(e.target.checked)} className="accent-orange-500" />
          <span>AI Off</span>
        </label>
      )}
      {mode === "career" && (
        <button
          onClick={save}
          disabled={busy}
          title="Snapshot the current career state. Anything you do without saving is discarded next time you enter Full GM Mode."
          className="px-2 py-0.5 rounded border border-emerald-700 text-emerald-300 hover:bg-emerald-900/30 disabled:opacity-50"
        >
          {savedAt && Date.now() - savedAt < 2500 ? "✓ Saved" : "💾 Save"}
        </button>
      )}
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
