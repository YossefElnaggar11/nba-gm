"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";

export function RenounceHoldButton({ holdId }: { holdId: number }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const onClick = async () => {
    if (!confirm("Renounce this cap hold? You'll lose Bird rights to re-sign this player.")) return;
    setBusy(true);
    try {
      await api.renounceHold(holdId);
      router.refresh();
    } finally {
      setBusy(false);
    }
  };
  return (
    <button
      onClick={onClick}
      disabled={busy}
      className="px-2 py-0.5 text-xs rounded bg-zinc-700 hover:bg-zinc-600 disabled:opacity-50"
    >
      Renounce
    </button>
  );
}
