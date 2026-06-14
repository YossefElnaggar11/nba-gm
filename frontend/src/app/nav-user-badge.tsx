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
    <header className="border-b border-zinc-800 bg-zinc-900/70 backdrop-blur sticky top-0 z-10">
      <nav className="max-w-7xl mx-auto px-6 py-2.5 flex items-center gap-6">
        <Link href="/" className="font-bold text-sm tracking-tight whitespace-nowrap">
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
    if (!confirm(
      "Hard reset the game?\n\n" +
      "• Wipes all current state\n" +
      "• Deletes your career save\n" +
      "• Takes you back to the 2026 offseason\n\n" +
      "This cannot be undone."
    )) {
      return;
    }
    setBusy(true);
    try {
      await api.reset();
      if (typeof window !== "undefined") {
        // Clear localStorage so the user's prior team/mode choice doesn't persist
        try {
          localStorage.removeItem("nba_gm_user_team");
          localStorage.removeItem("nba_gm_mode");
          localStorage.removeItem("nba_gm_career_mode");
        } catch {}
        window.location.href = "/";
      }
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
        <button
          onClick={reset}
          disabled={busy}
          title="Wipe the current state and start the 2026 offseason over from scratch."
          className="px-3 py-1 rounded border border-amber-700 bg-amber-900/20 text-amber-300 hover:bg-amber-900/40 disabled:opacity-50 font-medium"
        >
          {busy ? "Resetting…" : "↻ Reset Game"}
        </button>
        <Link href="/" className="text-zinc-500 hover:text-zinc-300">Pick a team →</Link>
      </div>
    );
  }
  return (
    <div className="ml-auto flex items-center gap-3 text-xs">
      <span className={`px-2 py-0.5 rounded font-medium uppercase tracking-wider ${
        mode === "career" ? "bg-orange-900/40 text-orange-300" : "bg-emerald-900/40 text-emerald-300"
      }`}>
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
      <button
        onClick={reset}
        disabled={busy}
        title="Hard reset — wipe everything and start the 2026 offseason over."
        className="px-3 py-1.5 rounded-md border-2 border-red-600 bg-red-900/30 text-red-200 hover:bg-red-700 hover:text-white disabled:opacity-50 font-bold text-xs uppercase tracking-wider shadow-lg shadow-red-900/30"
      >
        {busy ? "Resetting…" : "↻ Reset Game"}
      </button>
    </div>
  );
}

export function NavQuickLinks() {
  const { team, mode } = useUserContext();
  return (
    <div className="flex items-center gap-5 text-sm text-zinc-400">
      {team && (
        <Link
          href={`/team/${team}`}
          className="inline-flex items-center gap-2 hover:text-white transition font-medium group"
        >
          <span className="inline-flex items-center justify-center w-7 h-6 rounded bg-orange-500/15 border border-orange-500/40 text-orange-300 text-[10px] font-mono font-bold tracking-wider group-hover:bg-orange-500/25 transition">
            {team}
          </span>
          <span>My Team</span>
        </Link>
      )}
      {mode === "career" && (
        <>
          <Link href="/awards" className="hover:text-white transition">Awards</Link>
          <Link href="/leaders" className="hover:text-white transition">Leaders</Link>
        </>
      )}
    </div>
  );
}
