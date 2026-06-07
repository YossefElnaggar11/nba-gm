"use client";

import { useEffect, useState } from "react";

export type GameMode = "offseason" | "career";

export type UserContext = {
  team: string | null;
  mode: GameMode;
  ready: boolean;
};

export function useUserContext(): UserContext {
  const [team, setTeam] = useState<string | null>(null);
  const [mode, setMode] = useState<GameMode>("offseason");
  const [ready, setReady] = useState(false);
  useEffect(() => {
    if (typeof window === "undefined") return;
    setTeam(localStorage.getItem("nba_gm_user_team"));
    const m = localStorage.getItem("nba_gm_mode");
    setMode(m === "career" ? "career" : "offseason");
    setReady(true);
  }, []);
  return { team, mode, ready };
}

export function getUserTeam(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("nba_gm_user_team");
}

export function getUserMode(): GameMode {
  if (typeof window === "undefined") return "offseason";
  return localStorage.getItem("nba_gm_mode") === "career" ? "career" : "offseason";
}
