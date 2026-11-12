import { create } from "zustand";

type Filters = {
  product: string;
  dateFrom: string;
  dateTo: string;
  set: (p: Partial<Pick<Filters, "product" | "dateFrom" | "dateTo">>) => void;
  reset: () => void;
};

export const useFilters = create<Filters>((set) => ({
  product: "",
  dateFrom: "",
  dateTo: "",
  set: (p) => set(p),
  reset: () => set({ product: "", dateFrom: "", dateTo: "" }),
}));

/** Query string for the endpoints that accept product, date_from and date_to. */
export function filterQs(f: { product: string; dateFrom: string; dateTo: string }): string {
  const p = new URLSearchParams();
  if (f.product) p.set("product", f.product);
  if (f.dateFrom) p.set("date_from", f.dateFrom);
  if (f.dateTo) p.set("date_to", f.dateTo);
  const s = p.toString();
  return s ? "?" + s : "";
}
