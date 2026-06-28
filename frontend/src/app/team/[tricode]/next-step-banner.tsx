"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useUserContext } from "@/lib/user-context";

/**
 * Offseason guide. The user's home base for navigating the GM flow.
 *
 * Shows a clear "next action" CTA and a visual stepper of all offseason phases
 * (Draft → Options → Re-sign FAs → Free Agency → Sim Season). Each phase has
 * three states: done (✓ green), current (highlighted orange), todo (gray).
 *
 * Renders only for the user's own team in career mode.
 */

type StepStatus = "done" | "current" | "todo";

type Step = {
  id: string;
  label: string;          // Short label for the stepper pills
  fullLabel: string;      // Verbose label for the CTA
  href: string;
  status: StepStatus;
  detail?: string;
  countBadge?: number;    // optional small count next to label
};

export function NextStepBanner({ tricode }: { tricode: string }) {
  const { team: userTeam, mode } = useUserContext();
  const [data, setData] = useState<{
    currentSeason: string;
    draftYear: number;
    seasonSimmed: boolean;
    scopeDone: boolean;
    draftPicksLeft: number;
    draftPicksLeftForUser: number;
    optionsPending: number;
    ownFAs: number;
    standardCount: number;
  } | null>(null);

  const fetchState = async () => {
    if (!userTeam || userTeam !== tricode) return;
    try {
      const state = await api.state();
      const [opts, ownFAResp, nextP, roster] = await Promise.all([
        api.pendingOptions(tricode, state.current_season).catch(() => []),
        api.ownFAs(tricode).catch(() => ({ own_fas: [] })),
        api.nextPick(state.current_draft_year).catch(() => ({ done: true })),
        api.capSheet(tricode, state.current_season).catch(() => null),
      ]);
      let dLeft = 0;
      let userLeft = 0;
      if (!nextP.done) {
        try {
          const order = await api.draftOrder(state.current_draft_year);
          const remaining = order.filter(p => p.status === "OWNED" && p.pick_number !== null);
          dLeft = remaining.length;
          userLeft = remaining.filter(p => p.owner === tricode).length;
        } catch {
          dLeft = 1;
        }
      }
      const standardCount = roster ? roster.players.filter(p => !p.is_two_way).length : 0;
      setData({
        currentSeason: state.current_season,
        draftYear: state.current_draft_year,
        seasonSimmed: state.simmed_seasons.includes(state.current_season),
        scopeDone: state.scope_done,
        draftPicksLeft: dLeft,
        draftPicksLeftForUser: userLeft,
        optionsPending: opts.length,
        ownFAs: ownFAResp.own_fas.length,
        standardCount,
      });
    } catch { /* swallow */ }
  };

  useEffect(() => {
    fetchState();
    // Re-fetch when any action (re-sign, option decide, etc.) broadcasts a refresh.
    const listener = () => fetchState();
    if (typeof window !== "undefined") {
      window.addEventListener("nba-gm:data-changed", listener);
    }
    return () => {
      if (typeof window !== "undefined") {
        window.removeEventListener("nba-gm:data-changed", listener);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tricode, userTeam, mode]);

  if (userTeam !== tricode || !data) return null;

  if (mode === "career" && data.scopeDone && data.seasonSimmed) {
    return (
      <div className="rounded-xl border border-emerald-500/40 bg-gradient-to-br from-emerald-900/20 to-zinc-950 p-5 mb-6">
        <div className="text-2xl font-bold text-emerald-300">🏆 Career Complete</div>
        <p className="text-sm text-zinc-300 mt-1">All seasons in scope have been simulated. Check the Awards and Leaders pages to relive the runs.</p>
      </div>
    );
  }

  // Build the canonical sequence. The Draft step is only shown when there's
  // actual work to do — once all picks are conveyed (or the draft was already
  // pre-applied), the step is omitted entirely instead of sitting there as a
  // green ✓ taking up space.
  const steps: Step[] = [];
  if (data.draftPicksLeft > 0) {
    steps.push({
      id: "draft",
      label: "Draft",
      fullLabel: `${data.draftYear} NBA Draft`,
      href: `/draft/${data.draftYear}/live`,
      status: "current",
      detail: `${data.draftPicksLeftForUser} of your picks unmade · ${data.draftPicksLeft} left in the league`,
      countBadge: data.draftPicksLeftForUser || undefined,
    });
  }
  steps.push(
    {
      id: "options",
      label: "Options",
      fullLabel: "Player & Team Options",
      href: "/options",
      status: data.optionsPending > 0 ? "current" : "done",
      detail: data.optionsPending > 0
        ? `${data.optionsPending} pending decisions on your roster`
        : "Resolved",
      countBadge: data.optionsPending || undefined,
    },
    {
      id: "own-fas",
      label: "Own FAs",
      fullLabel: "Re-sign Your Free Agents",
      href: `/team/${tricode}#own-fas`,
      status: data.ownFAs > 0 ? "current" : "done",
      detail: data.ownFAs > 0
        ? `${data.ownFAs} Bird-rights free agents to re-sign or renounce`
        : "Handled",
      countBadge: data.ownFAs || undefined,
    },
    {
      id: "fa",
      label: "Free Agency",
      fullLabel: "Free Agency & Trades",
      href: "/free-agents",
      status: "current",
      detail: "Browse the market and work the phones — optional but recommended",
    },
  );
  const rosterOverflow = data.standardCount > 15;
  if (rosterOverflow) {
    // Insert a roster-trim step right before sim
    steps.push({
      id: "roster-trim",
      label: "Trim Roster",
      fullLabel: "Trim Your Roster",
      href: `/team/${tricode}`,
      status: "current",
      detail: `${data.standardCount} of max 15 standard contracts — release ${data.standardCount - 15} player(s) or move them in a trade`,
      countBadge: data.standardCount - 15,
    });
  }
  if (mode === "career") {
    const simBlocked = data.draftPicksLeft > 0 || rosterOverflow;
    steps.push({
      id: "sim",
      label: "Sim Season",
      fullLabel: `Sim the ${data.currentSeason} Season`,
      href: "/sim",
      status: data.seasonSimmed ? "done" : (!simBlocked ? "current" : "todo"),
      detail: data.seasonSimmed
        ? "Season simmed"
        : rosterOverflow
          ? `Blocked: ${data.standardCount}/15 standard contracts — release ${data.standardCount - 15} first`
          : data.draftPicksLeft > 0
            ? `Blocked until the ${data.draftYear} draft is complete`
            : "Ready to sim — run the season when you're done shopping",
    });
  }

  // Only ONE step should be "current" — the first remaining required action.
  // Free Agency is optional, so demote it to "todo" if any required step is still current.
  let foundCurrent = false;
  for (const s of steps) {
    if (s.status === "current") {
      if (foundCurrent) s.status = "todo";
      else foundCurrent = true;
    }
  }

  const cta = steps.find(s => s.status === "current") ?? steps[steps.length - 1];

  return (
    <div className="rounded-xl border border-orange-500/40 bg-gradient-to-br from-orange-950/30 via-zinc-950 to-zinc-950 p-5 mb-6 shadow-lg shadow-orange-500/5">
      {/* Primary CTA */}
      <div className="flex items-start justify-between gap-4 mb-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-[11px] uppercase tracking-widest text-orange-400 font-semibold mb-1">
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-orange-400 animate-pulse"></span>
            {mode === "career" ? `Next step · ${data.currentSeason} Offseason` : `2026 Offseason Sandbox`}
          </div>
          <h2 className="text-2xl font-bold tracking-tight">{cta.fullLabel}</h2>
          {cta.detail && <p className="text-sm text-zinc-400 mt-1">{cta.detail}</p>}
        </div>
        <Link
          href={cta.href}
          className="shrink-0 px-5 py-2.5 rounded-lg bg-orange-500 hover:bg-orange-400 text-black font-bold text-sm transition shadow-md shadow-orange-500/30"
        >
          Continue →
        </Link>
      </div>

      {/* Stepper */}
      <div className="flex flex-wrap items-stretch gap-1.5 text-xs">
        {steps.map((s, i) => {
          const isDone = s.status === "done";
          const isCurrent = s.status === "current";
          return (
            <div key={s.id} className="flex items-center gap-1.5 flex-1 min-w-[140px]">
              <Link
                href={s.href}
                className={`flex-1 flex items-center justify-between gap-2 px-3 py-2 rounded-md transition ${
                  isDone
                    ? "bg-emerald-900/30 text-emerald-300 hover:bg-emerald-900/50 border border-emerald-700/40"
                    : isCurrent
                    ? "bg-orange-500/15 text-orange-200 hover:bg-orange-500/25 border border-orange-500/60"
                    : "bg-zinc-800/40 text-zinc-500 hover:bg-zinc-800 border border-zinc-700/40"
                }`}
              >
                <span className="flex items-center gap-1.5 font-medium">
                  <span className={`w-5 h-5 rounded-full inline-flex items-center justify-center text-[10px] font-bold ${
                    isDone ? "bg-emerald-500 text-black" : isCurrent ? "bg-orange-500 text-black" : "bg-zinc-700 text-zinc-300"
                  }`}>
                    {isDone ? "✓" : i + 1}
                  </span>
                  {s.label}
                </span>
                {s.countBadge !== undefined && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-orange-500/30 text-orange-200 font-mono">
                    {s.countBadge}
                  </span>
                )}
              </Link>
              {i < steps.length - 1 && (
                <span className="text-zinc-700 text-base">→</span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
