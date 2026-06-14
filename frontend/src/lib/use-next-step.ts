"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useUserContext } from "@/lib/user-context";

/**
 * Hook used by every offseason phase page to compute the "Continue" button's
 * target. Looks at the same state the NextStepBanner does and picks the next
 * required step in the canonical order: Draft → Options → Own FAs → FA → Sim.
 *
 * `from` is the phase the user is currently on; the hook returns the FIRST
 * pending step *after* that one (or back to the team page if everything's done).
 */
export type PhaseId = "draft" | "options" | "own-fas" | "fa" | "sim";

type StepLink = { href: string; label: string };

const ORDER: PhaseId[] = ["draft", "options", "own-fas", "fa", "sim"];

export function useNextOffseasonStep(from: PhaseId): StepLink {
  const { team: userTeam, mode } = useUserContext();
  const [step, setStep] = useState<StepLink>({
    href: userTeam ? `/team/${userTeam}` : "/",
    label: userTeam ? "Done — back to team →" : "Home →",
  });

  useEffect(() => {
    if (!userTeam) {
      setStep({ href: "/", label: "Home →" });
      return;
    }
    (async () => {
      try {
        const s = await api.state();
        const seasonSimmed = s.simmed_seasons.includes(s.current_season);
        const draftYear = s.current_draft_year;
        const isCareer = mode === "career";

        const [opts, ownFAResp, order] = await Promise.all([
          api.pendingOptions(userTeam, s.current_season).catch(() => []),
          api.ownFAs(userTeam).catch(() => ({ own_fas: [] })),
          api.draftOrder(draftYear).catch(() => []),
        ]);

        const draftPicksLeft = order.filter(p => p.status === "OWNED" && p.pick_number !== null).length;

        // Build the status of each phase
        const status: Record<PhaseId, boolean> = {
          draft: draftPicksLeft === 0,
          options: opts.length === 0,
          "own-fas": ownFAResp.own_fas.length === 0,
          fa: from === "fa",                    // FA is "done" only when the user is on it
          sim: !isCareer || seasonSimmed,       // sim doesn't exist in offseason mode
        };

        // First pending step strictly *after* the current `from`
        const fromIdx = ORDER.indexOf(from);
        const remaining = ORDER.slice(fromIdx + 1);
        let nextPhase: PhaseId | null = null;
        for (const ph of remaining) {
          if (ph === "sim" && !isCareer) continue;
          if (!status[ph]) {
            nextPhase = ph;
            break;
          }
        }

        if (nextPhase === "draft") {
          setStep({ href: `/draft/${draftYear}/live`, label: "Continue to the draft →" });
        } else if (nextPhase === "options") {
          setStep({ href: "/options", label: "Continue to options →" });
        } else if (nextPhase === "own-fas") {
          setStep({ href: `/team/${userTeam}#own-fas`, label: "Re-sign your own FAs →" });
        } else if (nextPhase === "fa") {
          setStep({ href: "/free-agents", label: "Continue to free agency →" });
        } else if (nextPhase === "sim") {
          setStep({ href: "/sim", label: "Sim the season →" });
        } else if (from === "fa" && isCareer && !seasonSimmed) {
          // From the FA page, the natural next step is sim
          setStep({ href: "/sim", label: "Sim the season →" });
        } else {
          setStep({ href: `/team/${userTeam}`, label: "Done — back to team →" });
        }
      } catch {
        setStep({ href: `/team/${userTeam}`, label: "Done — back to team →" });
      }
    })();
  }, [userTeam, mode, from]);

  return step;
}
