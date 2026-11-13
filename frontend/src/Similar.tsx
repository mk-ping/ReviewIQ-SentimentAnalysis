import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";

type SimilarData = {
  items: { review_id: number; product: string; stars: number | null; text: string; similarity: number }[];
  note: string;
};

export default function Similar({ id }: { id: number }) {
  const [open, setOpen] = useState(false);
  const q = useQuery({
    queryKey: ["similar", id], enabled: open, retry: false,
    queryFn: () => api<SimilarData>(`/reviews/similar/${id}?limit=5`),
  });
  return (
    <div className="mt-2">
      <button className="text-xs text-indigo-600 underline" onClick={() => setOpen(!open)}>
        {open ? "Hide similar reviews" : "Find similar reviews"}
      </button>
      {open && (
        <div className="mt-2 rounded-md bg-slate-50 p-2 text-xs">
          {q.isLoading && <p className="text-slate-500">Searching...</p>}
          {q.error && <p className="text-amber-700">No similar-review index for this review yet. Run the analysis on the Upload page, which now builds it.</p>}
          {q.data && q.data.items.length === 0 && <p className="text-slate-500">Nothing similar found.</p>}
          <ul className="space-y-1">
            {q.data?.items.map((s) => (
              <li key={s.review_id}>
                <span className="text-slate-400">{(s.similarity * 100).toFixed(0)}% similar | {s.product} | {s.stars ?? "no"} stars | </span>
                {s.text}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
