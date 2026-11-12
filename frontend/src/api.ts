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

export type RatingVsTextData = {
  n: number; low_sample: boolean; agreement_rate: number | null; mismatches: number;
  underrated: number; overrated: number; mean_abs_star_gap: number | null; big_gap_share: number | null;
  by_star: { stars: number; reviews: number; avg_text_stars: number | null }[]; note: string;
};
export type MismatchList = {
  total: number; next_after_id: number | null;
  items: { review_id: number; product: string; stars: number | null; fused_stars: number | null;
           predicted_stars: number | null; star_gap: number | null; type: string; text: string }[];
};
export type HiddenData = {
  hidden_reviews: number; rated_4plus_analysed: number; hidden_rate: number | null; low_sample: boolean;
  blind_spots: { aspect: string; negative_mentions: number; in_4_5_star: number; blind_spot_share: number; low_sample: boolean }[];
  items: { review_id: number; product: string; stars: number | null; text: string;
           negative_mentions: { aspect: string; term: string; phrase: string; sentiment: number }[] }[];
};

export async function send<T>(method: "POST" | "PATCH", path: string, body?: unknown): Promise<T> {
  const r = await fetch("/api" + path, {
    method, headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!r.ok) {
    let msg = `${r.status} ${path}`;
    try { msg = (await r.json()).detail ?? msg; } catch { /* keep default */ }
    throw new Error(msg);
  }
  return r.json();
}

export type Issue = {
  issue_id: number; name: string; aspect: string; keywords: string[]; reviews: number; low_sample: boolean;
  frequency: number; severity: number; growth: number; rating_gain: number; hidden_share: number | null;
  priority_score: number; evidence: { review_id: number; quote: string }[];
};
export type WhatIf = {
  issues: string[]; reviews_affected: number; rated_reviews: number; current_avg: number | null;
  estimated_avg: number | null; estimated_gain: number | null; low_sample: boolean; assumption: string;
};
export type ActionRow = {
  action_id: number; aspect: string; issue: string; suggested_action: string; owner: string | null;
  effort: string | null; status: string; impact_note: string | null;
};
export type Recommendation = {
  issue_id: number; issue: string; aspect: string; suggested_action: string; owner_team: string;
  existing_action_id: number | null;
};
export type AspectRow = {
  aspect: string; mentions: number; reviews: number; avg_sentiment: number;
  negative: number; positive: number; neutral: number; low_sample: boolean;
};
export type Drivers = {
  stars: number[]; reviews_in_range: number; reviews_elsewhere: number; low_sample: boolean; note: string;
  drivers: { aspect: string; reviews_in_range: number; share_in_range: number | null; share_elsewhere: number | null; avg_sentiment_in_range: number | null }[];
};
export type ReviewItem = {
  review_id: number; product: string; stars: number | null; date: string | null; language: string | null;
  text: string; text_label: string | null; fused_stars: number | null; mismatch: string | null;
  negative_phrases: { aspect: string; term: string; phrase: string; sentiment: number }[];
};
export type ReviewPage = { items: ReviewItem[]; next_after_id: number | null };
