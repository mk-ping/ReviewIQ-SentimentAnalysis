export function Logo({ size = 28 }: { size?: number }) {
  return (
    <span className="grid place-items-center rounded-lg bg-gradient-to-br from-accent to-accent2" style={{ width: size, height: size }}>
      <svg width={size * 0.6} height={size * 0.6} viewBox="0 0 24 24" fill="none" stroke="#07080b" strokeWidth="3" strokeLinecap="round">
        <path d="M5 19V11M12 19V5M19 19v-5" />
      </svg>
    </span>
  );
}

export function Wordmark() {
  return (
    <span className="flex items-center gap-2 text-base font-semibold tracking-tight text-slate-900">
      <Logo /> ReviewIQ
    </span>
  );
}

const ICONS: Record<string, string> = {
  home: "M3 11l9-8 9 8v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z",
  smile: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M8 14s1.5 2 4 2 4-2 4-2 M9 9.5h.01 M15 9.5h.01",
  gap: "M7 4v16 M17 4v16 M3 8l4-4 4 4 M13 16l4 4 4-4",
  layers: "M12 3l9 5-9 5-9-5z M3 13l9 5 9-5",
  alert: "M12 3l10 18H2z M12 10v5 M12 18h.01",
  compare: "M4 20V10 M10 20V4 M16 20v-8 M22 20H2",
  trend: "M3 17l6-6 4 4 8-8 M15 7h6v6",
  star: "M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z",
  search: "M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14z M21 21l-4.3-4.3",
  upload: "M12 16V4 M7 9l5-5 5 5 M4 20h16",
  tag: "M20 12l-8 8-9-9V3h8z M7.5 7.5h.01",
  file: "M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8z M14 3v5h5 M9 13h6 M9 17h6",
  logout: "M9 21H5a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h4 M16 17l5-5-5-5 M21 12H9",
  menu: "M4 6h16 M4 12h16 M4 18h16",
  globe: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M3 12h18 M12 3c3 3 3 15 0 18 M12 3c-3 3-3 15 0 18",
  bolt: "M13 2L4 14h7l-1 8 9-12h-7z",
  check: "M5 12l5 5 9-10",
};

export function Icon({ name, size = 16 }: { name: string; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
         strokeLinecap="round" strokeLinejoin="round" className="shrink-0">
      <path d={ICONS[name] ?? ICONS.star} />
    </svg>
  );
}
