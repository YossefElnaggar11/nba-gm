"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useUserContext } from "@/lib/user-context";

function pathToPhase(path: string): string | null {
  if (path.startsWith("/options")) return "options";
  if (path.startsWith("/free-agents")) return "fa";
  if (path.startsWith("/draft") && path.includes("/live")) return "draft";
  if (path.startsWith("/sim")) return "sim";
  return null;
}

function usePhases() {
  const { mode } = useUserContext();
  const [draftYear, setDraftYear] = useState(2026);
  const [currentSeason, setCurrentSeason] = useState("2026-27");
  const [simmedSeasons, setSimmedSeasons] = useState<string[]>([]);
  const [scopeDone, setScopeDone] = useState(false);
  useEffect(() => {
    api.state().then(s => {
      setDraftYear(s.current_draft_year);
      setCurrentSeason(s.current_season);
      setSimmedSeasons(s.simmed_seasons);
      setScopeDone(s.scope_done);
    }).catch(() => {});
  }, []);
  // Sequential order per user spec: Draft -> Options -> Free Agency -> Sim
  const phases = [
    { id: "draft", label: "1. Draft", href: `/draft/${draftYear}/live` },
    { id: "options", label: "2. Options", href: "/options" },
    { id: "fa", label: "3. Free Agency & Trades", href: "/free-agents" },
  ];
  if (mode === "career") phases.push({ id: "sim", label: "4. Sim Season", href: "/sim" });
  return { phases, draftYear, currentSeason, simmedSeasons, scopeDone };
}

export function PhaseNav() {
  const path = usePathname();
  const current = pathToPhase(path);
  const { phases, currentSeason } = usePhases();
  if (!current) return null;
  return (
    <div className="bg-zinc-900/50 border border-zinc-800 rounded-lg p-2 mb-4 flex items-center justify-between gap-1 text-xs">
      <div className="flex items-center gap-1">
        {phases.map((p, i) => {
          const isActive = p.id === current;
          const idx = phases.findIndex((q) => q.id === current);
          const isPast = idx >= 0 && i < idx;
          return (
            <span key={p.id} className="flex items-center gap-1">
              <Link
                href={p.href}
                className={`px-2.5 py-1 rounded font-medium transition ${
                  isActive ? "bg-orange-500 text-black"
                  : isPast ? "text-emerald-400 hover:bg-zinc-800"
                  : "text-zinc-500 hover:bg-zinc-800"
                }`}
              >
                {p.label}
              </Link>
              {i < phases.length - 1 && <span className="text-zinc-700">→</span>}
            </span>
          );
        })}
      </div>
      <div className="text-zinc-500 pr-2">
        Offseason: <span className="text-zinc-300 font-mono">{currentSeason}</span>
      </div>
    </div>
  );
}

export function NextPhaseButton({ from }: { from: "options" | "fa" | "draft" | "sim" }) {
  const { phases } = usePhases();
  const idx = phases.findIndex((p) => p.id === from);
  if (idx === -1 || idx === phases.length - 1) return null;
  const next = phases[idx + 1];
  return (
    <Link
      href={next.href}
      className="inline-flex items-center gap-2 px-4 py-2 rounded-md bg-orange-500 hover:bg-orange-400 text-black font-semibold text-sm transition"
    >
      Next: {next.label} →
    </Link>
  );
}
