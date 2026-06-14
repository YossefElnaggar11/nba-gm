"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { api, type NextPick, type Prospect } from "@/lib/api";
import { useUserContext } from "@/lib/user-context";
import { useNextOffseasonStep } from "@/lib/use-next-step";
import { BackButton } from "@/app/back-button";

export default function LiveDraftPage({ params }: { params: Promise<{ year: string }> }) {
  const { year } = use(params);
  const yearNum = parseInt(year, 10);
  const { team: ctxTeam, ready } = useUserContext();
  const [userTeam, setUserTeam] = useState<string>("");
  const nextStep = useNextOffseasonStep("draft");
  const [next, setNext] = useState<NextPick | null>(null);
  const [prospects, setProspects] = useState<Prospect[]>([]);
  const [recentPicks, setRecentPicks] = useState<Array<{ pick: number; round: number; team: string; player: string; overall: number | null }>>([]);
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    const [n, p] = await Promise.all([api.nextPick(yearNum), api.prospects(yearNum, true)]);
    setNext(n);
    setProspects(p);
  };

  useEffect(() => {
    refresh();
  }, [yearNum]);

  useEffect(() => {
    if (ready && ctxTeam) setUserTeam(ctxTeam);
  }, [ready, ctxTeam]);

  if (ready && !ctxTeam) {
    return (
      <div className="max-w-2xl mx-auto px-6 py-16 text-center">
        <p className="text-zinc-400 mb-4">You haven&apos;t picked a team yet.</p>
        <Link href="/" className="px-4 py-2 rounded bg-orange-500 text-black font-semibold">Pick your team →</Link>
      </div>
    );
  }

  const draft = async (prospect_id: number) => {
    if (!next?.pick_id) return;
    setBusy(true);
    try {
      const r = await api.makePick(next.pick_id, prospect_id);
      setRecentPicks([{
        pick: r.pick_number, round: r.round, team: r.team,
        player: r.player.name, overall: r.player.overall,
      }, ...recentPicks].slice(0, 30));
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  const autoOne = async () => {
    setBusy(true);
    try {
      const r = await api.autoPick(yearNum);
      if (!r.done && r.team) {
        setRecentPicks([{
          pick: r.pick_number ?? 0, round: 1, team: r.team,
          player: r.player?.name ?? "?", overall: r.player?.overall ?? null,
        }, ...recentPicks].slice(0, 30));
      }
      await refresh();
    } finally { setBusy(false); }
  };

  const simToMe = async () => {
    setBusy(true);
    try {
      await api.autoSimUntil(yearNum, userTeam);
      await refresh();
      // Recent picks list won't update from this — limitation. Reload to see all.
    } finally { setBusy(false); }
  };

  const onTheClock = next?.owner === userTeam;
  const draftOver = next?.done;

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      <BackButton />
      <div className="flex items-center justify-between mb-6 gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{yearNum} NBA Draft — Live</h1>
          <p className="text-zinc-400 mt-1">
            You GM <span className="text-orange-400 font-mono font-bold">{userTeam}</span>. The AI auto-picks for the other 29 teams.
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Link href="/trade" className="px-3 py-1.5 rounded bg-zinc-800 hover:bg-zinc-700 text-sm">
            🔄 Draft-Day Trade
          </Link>
          {draftOver && userTeam && (
            <Link href={nextStep.href} className="px-4 py-2 rounded-md bg-orange-500 hover:bg-orange-400 text-black font-semibold text-sm">
              {nextStep.label}
            </Link>
          )}
        </div>
      </div>

      {draftOver ? (
        <div className="bg-emerald-900/20 border border-emerald-700 rounded-lg p-6 text-center text-emerald-300">
          🏆 Draft Complete!
        </div>
      ) : (
        <div className={`rounded-xl p-5 mb-6 border ${onTheClock ? "border-orange-500 bg-orange-500/10" : "border-zinc-700 bg-zinc-900"}`}>
          <div className="flex items-center justify-between">
            <div>
              <div className="text-xs uppercase tracking-wider text-zinc-400">
                On the clock — Pick #{next?.pick_number} (R{next?.round})
              </div>
              <div className="text-3xl font-bold mt-1">
                {next?.owner}
                {next?.original !== next?.owner && (
                  <span className="text-base text-zinc-500 ml-2 font-normal">(from {next?.original})</span>
                )}
              </div>
              {onTheClock && (
                <div className="text-orange-400 font-semibold mt-1">YOU&apos;RE ON THE CLOCK</div>
              )}
            </div>
            <div className="flex gap-2">
              {!onTheClock && (
                <button onClick={autoOne} disabled={busy} className="px-4 py-2 rounded bg-zinc-800 hover:bg-zinc-700 text-sm disabled:opacity-50">
                  Auto-pick this one
                </button>
              )}
              {!onTheClock && (
                <button onClick={simToMe} disabled={busy} className="px-4 py-2 rounded bg-orange-500 hover:bg-orange-400 text-black text-sm font-semibold disabled:opacity-50">
                  Sim to my pick →
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-zinc-900 border border-zinc-800 rounded-lg p-5">
          <h2 className="text-lg font-semibold mb-4">Best Available ({prospects.length})</h2>
          <div className="space-y-1 max-h-[600px] overflow-y-auto">
            {prospects.map(p => (
              <div key={p.id} className="flex items-center gap-3 p-2 rounded hover:bg-zinc-800/40 text-sm">
                <span className="font-mono text-xs text-zinc-500 w-8 text-right">#{p.rank}</span>
                <div className="flex-1">
                  <div className="font-medium">{p.name}</div>
                  <div className="text-xs text-zinc-500">{p.position} · {p.college} · {p.age}yo</div>
                </div>
                <div className="text-right">
                  <div className="text-xs"><span className="text-zinc-500">OVR</span> <span className="font-mono text-zinc-200">{p.overall}</span></div>
                  <div className="text-xs"><span className="text-zinc-500">POT</span> <span className="font-mono text-emerald-400">{p.potential}</span></div>
                </div>
                {onTheClock && (
                  <button
                    onClick={() => draft(p.id)}
                    disabled={busy}
                    className="ml-2 px-3 py-1 text-xs rounded bg-orange-500 hover:bg-orange-400 text-black font-semibold disabled:opacity-50"
                  >
                    Draft
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>

        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
          <h2 className="text-lg font-semibold mb-4">Recent Picks</h2>
          {recentPicks.length === 0 ? (
            <div className="text-xs text-zinc-500">No picks yet this session.</div>
          ) : (
            <div className="space-y-2">
              {recentPicks.map((p, i) => (
                <div key={i} className="text-sm border-b border-zinc-800/50 pb-2">
                  <div className="text-xs text-zinc-500">Pick #{p.pick} · {p.team}</div>
                  <div className="font-medium">{p.player}</div>
                  {p.overall && <div className="text-xs text-zinc-500">OVR {p.overall}</div>}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
