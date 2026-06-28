import Link from "next/link";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";
export const revalidate = 0;
export const fetchCache = "force-no-store";

export default async function DraftPage({ params }: { params: Promise<{ year: string }> }) {
  const { year } = await params;
  const yearNum = parseInt(year, 10);
  let picks: Awaited<ReturnType<typeof api.draftOrder>>;
  try {
    picks = await api.draftOrder(yearNum);
  } catch {
    return (
      <div className="max-w-2xl mx-auto px-6 py-16 text-center">
        <h1 className="text-2xl font-bold mb-3">Waking up the backend…</h1>
        <p className="text-zinc-400">
          The free-tier server takes ~30 seconds to spin up after inactivity.
          Refresh the page in a moment.
        </p>
      </div>
    );
  }
  const r1 = picks.filter((p) => p.round === 1);
  const r2 = picks.filter((p) => p.round === 2);
  // "Live draft" only makes sense if there are still picks to make. Once the
  // draft is over (e.g. the real 2026 draft, which we auto-apply at seed),
  // suppress the action button and show a "Complete" badge instead.
  const remainingPicks = picks.filter((p) => p.status === "OWNED" && p.pick_number !== null).length;
  const draftComplete = remainingPicks === 0;

  return (
    <div className="max-w-5xl mx-auto px-6 py-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
            {yearNum} NBA Draft
            {draftComplete && (
              <span className="text-xs px-2 py-0.5 rounded bg-emerald-900/40 text-emerald-300 font-medium uppercase tracking-wider">
                Complete
              </span>
            )}
          </h1>
          <p className="text-zinc-400 mt-1">
            {yearNum === 2026 && (draftComplete
              ? "Draft was held June 25-26, 2026. Read-only — picks already conveyed."
              : "June 25-26, 2026. Lottery held May 10.")}
          </p>
        </div>
        <div className="flex items-center gap-2 text-sm">
          {[2026, 2027, 2028, 2029, 2030].map((y) => (
            <Link
              key={y}
              href={`/draft/${y}`}
              className={`px-3 py-1.5 rounded ${y === yearNum ? "bg-orange-500 text-black font-medium" : "bg-zinc-800 text-zinc-300 hover:bg-zinc-700"}`}
            >
              {y}
            </Link>
          ))}
          {yearNum <= 2027 && !draftComplete && (
            <Link href={`/draft/${yearNum}/live`} className="ml-3 px-3 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500 text-white font-medium">
              Run Live Draft →
            </Link>
          )}
        </div>
      </div>

      <Round title="Round 1" picks={r1} />
      <Round title="Round 2" picks={r2} />
    </div>
  );
}

function Round({ title, picks }: { title: string; picks: Awaited<ReturnType<typeof api.draftOrder>> }) {
  if (picks.length === 0) return null;
  return (
    <div className="mb-8">
      <h2 className="text-sm uppercase tracking-wider text-zinc-500 mb-3">{title}</h2>
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-zinc-800/50 text-xs uppercase tracking-wider text-zinc-500">
            <tr>
              <th className="text-left px-4 py-2 w-12">#</th>
              <th className="text-left px-4 py-2 w-24">Owner</th>
              <th className="text-left px-4 py-2">Via</th>
              <th className="text-left px-4 py-2">Notes</th>
            </tr>
          </thead>
          <tbody>
            {picks.map((p) => (
              <tr key={p.id} className="border-t border-zinc-800/50 hover:bg-zinc-800/30">
                <td className="px-4 py-2 font-mono text-zinc-400">{p.pick_number ?? "—"}</td>
                <td className="px-4 py-2 font-semibold">{p.owner}</td>
                <td className="px-4 py-2 text-zinc-400">
                  {p.original !== p.owner ? (
                    <span>
                      from <span className="text-zinc-200">{p.original}</span>
                      {p.is_swap && <span className="ml-1 text-xs px-1.5 py-0.5 rounded bg-purple-900/40 text-purple-300">SWAP</span>}
                    </span>
                  ) : (
                    <span className="text-zinc-600">own pick</span>
                  )}
                </td>
                <td className="px-4 py-2 text-xs text-zinc-500">
                  {p.protection ? <span className="text-yellow-400">{p.protection}</span> : null}
                  {p.notes && <span className="ml-2">{p.notes}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
