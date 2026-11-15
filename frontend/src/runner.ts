export type Job = { job_id: number; status: string; progress: number; error: string | null };

export async function call(method: string, path: string) {
  const r = await fetch("/api" + path, { method });
  let data: any = null;
  try { data = await r.json(); } catch { /* not json */ }
  return { ok: r.ok, status: r.status, data };
}

export function runJob(jobId: number, onProgress: (j: Job) => void): Promise<Job> {
  return new Promise((resolve, reject) => {
    const es = new EventSource(`/api/jobs/${jobId}/events`);
    es.onmessage = (e) => {
      const j = JSON.parse(e.data) as Job;
      onProgress(j);
      if (j.status === "done") { es.close(); resolve(j); }
      if (j.status === "failed") { es.close(); reject(new Error(j.error ?? "Job failed")); }
    };
    es.onerror = () => { es.close(); reject(new Error("Lost the progress stream. Is the worker running?")); };
  });
}

// Stage names double as the API path: POST /uploads/{id}/{stage}
export const ALL_STAGES = ["score", "aspects", "issues", "embed"] as const;
export const STAGE_LABEL: Record<string, string> = {
  score: "Reading sentiment", aspects: "Finding aspects", issues: "Grouping problems", embed: "Indexing for search",
};
