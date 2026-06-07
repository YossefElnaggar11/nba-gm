"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, type Team } from "@/lib/api";

const MODE_LABEL: Record<string, { name: string; color: string }> = {
  offseason: { name: "2026 Offseason Mode", color: "emerald" },
  career: { name: "Full GM Mode", color: "orange" },
};

export default function TeamSetupPage() {
  const router = useRouter();
  const sp = useSearchParams();
  const mode = sp.get("mode") || "offseason";
  const label = MODE_LABEL[mode] || MODE_LABEL.offseason;
  const [teams, setTeams] = useState<Team[]>([]);

  useEffect(() => { api.teams().then(setTeams); }, []);

  const pick = (tricode: string) => {
    if (typeof window !== "undefined") {
      localStorage.setItem("nba_gm_user_team", tricode);
      localStorage.setItem("nba_gm_mode", mode);
      localStorage.setItem("nba_gm_career_mode", mode === "career" ? "true" : "false");
    }
    router.push(`/team/${tricode}`);
  };

  const east = teams.filter((t) => t.conference === "East");
  const west = teams.filter((t) => t.conference === "West");

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      <div className="mb-8">
        <Link href="/" className="text-xs text-zinc-500 hover:text-zinc-300">← Back to modes</Link>
        <div className="flex items-center gap-3 mt-2">
          <span className={`text-xs px-2 py-0.5 rounded bg-${label.color}-900/40 text-${label.color}-300 font-medium uppercase tracking-wider`}>{label.name}</span>
        </div>
        <h1 className="text-3xl font-bold tracking-tight mt-2">Pick the team you&apos;ll represent</h1>
        <p className="text-zinc-400 mt-1">This is your team for the duration of the game.</p>
      </div>

      <Section title="Eastern Conference" teams={east} onPick={pick} />
      <Section title="Western Conference" teams={west} onPick={pick} />
    </div>
  );
}

function Section({ title, teams, onPick }: { title: string; teams: Team[]; onPick: (t: string) => void }) {
  return (
    <div className="mb-10">
      <h2 className="text-sm uppercase tracking-wider text-zinc-500 mb-3">{title}</h2>
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
        {teams.map((t) => (
          <button
            key={t.tricode}
            onClick={() => onPick(t.tricode)}
            className="group relative overflow-hidden rounded-lg border border-zinc-800 hover:border-orange-500 transition aspect-[5/3] flex items-center justify-center p-4"
            style={{ background: `linear-gradient(135deg, ${t.primary_color} 0%, ${t.secondary_color} 100%)` }}
          >
            <div className="absolute inset-0 bg-black/30 group-hover:bg-black/10 transition" />
            {t.logo_url && (
              <img src={t.logo_url} alt={t.full_name} className="relative w-16 h-16 object-contain drop-shadow-lg group-hover:scale-110 transition" />
            )}
            <div className="absolute bottom-2 left-3 right-3 flex items-end justify-between">
              <div className="font-bold text-xl tracking-tight text-white drop-shadow-lg">{t.tricode}</div>
              <div className="text-[10px] text-white/80 drop-shadow truncate text-right">{t.full_name}</div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
