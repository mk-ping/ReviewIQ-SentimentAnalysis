export async function api<T>(path: string): Promise<T> {
  const r = await fetch("/api" + path);
  if (!r.ok) throw new Error(`${r.status} ${path}`);
  return r.json();
}

export type Summary = {
  reviews: number; rated_reviews: number; scored_reviews: number; low_sample: boolean;
  average_rating: number | null; weighted_rating: number | null; net_sentiment: number | null;
  percent_negative: number | null; mismatch_rate: number | null;
  top_problems: { issue: string; reviews: number; priority_score: number }[];
  top_strengths: { aspect: string; positive_mentions: number; avg_sentiment: number }[];
};
export type Distribution = {
  n: number; low_sample: boolean; audience: string | null;
  histogram: { stars: number; count: number; share: number }[];
};
export type TrueRating = {
  product: string; n: number; low_sample: boolean; shown_avg: number; true_rating: number;
  gap: number; clear_difference: boolean;
};
