"use client";

import { useEffect, useState } from "react";

/**
 * In Career Mode, AI on the opposing teams evaluates trades and FAs reject
 * lowball offers. The user can disable this for a sandbox-y experience while
 * still tracking career stats. Persisted in localStorage.
 */
const KEY = "nba_gm_ai_veto_disabled";

export function useAiVetoDisabled(): [boolean, (v: boolean) => void] {
  const [disabled, setDisabled] = useState(false);
  useEffect(() => {
    if (typeof window === "undefined") return;
    setDisabled(localStorage.getItem(KEY) === "true");
  }, []);
  const update = (v: boolean) => {
    setDisabled(v);
    if (typeof window !== "undefined") {
      localStorage.setItem(KEY, v ? "true" : "false");
    }
  };
  return [disabled, update];
}

export function getAiVetoDisabled(): boolean {
  if (typeof window === "undefined") return false;
  return localStorage.getItem(KEY) === "true";
}
