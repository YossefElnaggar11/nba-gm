"use client";

import { useState } from "react";
import { api } from "@/lib/api";

export function HomeResetButton() {
  const [busy, setBusy] = useState(false);

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
        try {
          localStorage.removeItem("nba_gm_user_team");
          localStorage.removeItem("nba_gm_mode");
          localStorage.removeItem("nba_gm_career_mode");
        } catch {}
        window.location.reload();
      }
    } finally { setBusy(false); }
  };

  return (
    <button
      onClick={reset}
      disabled={busy}
      title="Hard reset — wipe everything (including your career save) and start over from the 2026 offseason."
      className="px-4 py-2 rounded-md border-2 border-red-600 bg-red-900/30 text-red-200 hover:bg-red-700 hover:text-white disabled:opacity-50 font-bold text-xs uppercase tracking-wider shadow-lg shadow-red-900/30"
    >
      {busy ? "Resetting…" : "↻ Reset Game"}
    </button>
  );
}
