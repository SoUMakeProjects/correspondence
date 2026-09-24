import type { CSSProperties } from "react";

export type IconName =
  | "worklist"
  | "cases"
  | "mail"
  | "report"
  | "search"
  | "user"
  | "loan"
  | "home"
  | "client"
  | "file"
  | "download"
  | "chevron"
  | "check"
  | "clock"
  | "edit"
  | "follow"
  | "arrow"
  | "help"
  | "settings"
  | "close"
  | "send"
  | "shield"
  | "link"
  | "pause"
  | "refresh";
const paths: Record<IconName, string> = {
  worklist: "M5 3h14v18H5z M8 7h8 M8 11h8 M8 15h5",
  cases: "M4 6h5l2 2h9v12H4z M7 3h5l2 2h6 M8 11v6 M12 11v6 M16 11v6",
  mail: "M3 5h18v14H3z M3 6l9 7 9-7",
  report: "M4 3v17h17 M8 16v-5 M12 16V6 M16 16V9 M20 16V4",
  search: "M10.5 3a7.5 7.5 0 1 0 0 15 7.5 7.5 0 0 0 0-15 M16 16l5 5",
  user: "M12 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M5 21v-3a7 7 0 0 1 14 0v3z",
  loan: "M6 3h12v18H6z M10 7h4 M10 11h4 M11 17h2",
  home: "M3 11l9-8 9 8 M5 10v11h5v-7h4v7h5V10",
  client: "M5 21V8h14v13 M9 8V3h6v5 M8 12h2 M14 12h2 M8 16h2 M14 16h2 M3 21h18",
  file: "M6 3h8l5 5v13H6z M14 3v6h5 M9 13h7 M9 17h7",
  download: "M12 3v12 M7 10l5 5 5-5 M5 19v2h14v-2",
  chevron: "M9 5l7 7-7 7",
  refresh: "M19 8a8 8 0 1 0 1 6 M20 3v5h-5",
  check: "M5 12l4 4L19 6",
  clock: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18 M12 7v6l4 2",
  edit: "M14 4l6 6 M4 20l5-1L21 7l-5-5L4 14z",
  follow: "M4 17l8-8h7 M14 4l5 5-5 5 M4 8h3 M4 4h5",
  arrow: "M4 12h16 M15 7l5 5-5 5",
  help: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18 M9 9a3 3 0 1 1 4 3c-1 .5-1 1-1 2 M12 17h.01",
  settings: "M4 7h16 M4 17h16 M8 4v6 M16 14v6",
  close: "M6 6l12 12 M6 18L18 6",
  send: "M3 3l18 9-18 9 4-9z M7 12h14",
  shield: "M12 3l8 3v6c0 5-8 9-8 9s-8-4-8-9V6z M8 12l3 3 5-6",
  link: "M10 7l3-3a5 5 0 0 1 7 7l-3 3 M14 17l-3 3a5 5 0 0 1-7-7l3-3 M8 16l8-8",
  pause: "M8 4v16 M16 4v16",
};
export default function DeskIcon({
  name,
  size = 18,
  style,
}: {
  name: IconName;
  size?: number;
  style?: CSSProperties;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      style={style}
    >
      <path d={paths[name]} />
    </svg>
  );
}
