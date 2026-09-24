export type MailIconName =
  | "apps"
  | "mail"
  | "search"
  | "menu"
  | "chevron"
  | "close"
  | "inbox"
  | "send"
  | "draft"
  | "delete"
  | "archive"
  | "report"
  | "sweep"
  | "folder"
  | "reply"
  | "replyAll"
  | "read"
  | "flag"
  | "pin"
  | "print"
  | "refresh"
  | "more"
  | "filter"
  | "check"
  | "settings"
  | "help"
  | "bell"
  | "person"
  | "attach"
  | "file"
  | "star"
  | "undo"
  | "download";

const paths: Record<MailIconName, string> = {
  apps: "M3 3h2v2H3z M9 3h2v2H9z M15 3h2v2h-2z M3 9h2v2H3z M9 9h2v2H9z M15 9h2v2h-2z M3 15h2v2H3z M9 15h2v2H9z M15 15h2v2h-2z",
  mail: "M3 4.5h14a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1v-9a1 1 0 0 1 1-1z M2.5 5.5l7.5 5 7.5-5",
  search: "M8.5 2.5a6 6 0 1 0 0 12 6 6 0 0 0 0-12 M13 13l4.5 4.5",
  menu: "M3 5h14 M3 10h14 M3 15h14",
  chevron: "M5 7.5l5 5 5-5",
  close: "M5 5l10 10 M5 15L15 5",
  inbox:
    "M4 3.5h12l2 7v5a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1v-5z M2 10.5h5l1 3h4l1-3h5",
  send: "M2 2.5l16 7.5-16 7.5 3-7.5z M5 10h13",
  draft: "M10 3H4v14h12v-6 M8 10l7-7 2 2-7 7H8z",
  delete: "M3 5h14 M7 5V2.5h6V5 M5 5l.7 12h8.6L15 5 M8 8v6 M12 8v6",
  archive: "M2.5 3h15v4h-15z M4 7v10h12V7 M8 10h4",
  report: "M10 2l7 3v5c0 4-7 8-7 8s-7-4-7-8V5z M10 6v5 M10 14v.1",
  sweep: "M14 2L7 11 M5 10l7 5-3 3-7-5z M14 10h4 M16 14h2 M13 18h5",
  folder: "M2 5V3h6l2 2h8v11H2z M9 10h6 M12 7l3 3-3 3",
  reply: "M8 4L2 9l6 5 M2 9h9c4 0 6 2 6 6",
  replyAll: "M6 4L1 9l5 5 M11 4L6 9l5 5 M6 9h7c3 0 5 2 5 6",
  read: "M2 8l8-6 8 6v9H2z M2 8l8 6 8-6 M2 17l5-5 M18 17l-5-5",
  flag: "M4 18V3c4-3 8 3 12 0v8c-4 3-8-3-12 0",
  pin: "M7 2h6l-1 5 4 4v2H4v-2l4-4z M10 13v5",
  print: "M5 7V2h10v5 M5 14H2V7h16v7h-3 M5 11h10v7H5z M15 9h1",
  refresh: "M16 6a7 7 0 1 0 1 7 M16 2v5h-5",
  more: "M4 10h.1 M10 10h.1 M16 10h.1",
  filter: "M3 5h14 M6 10h8 M8 15h4",
  check: "M3 10l4 4L17 4",
  settings:
    "M8 2h4l.6 3 2 .9 2.6-1 2 3.4-2 2 .1 2.2 2 2-2 3.5-2.7-1-2 1L12 21H8l-.6-3-2-1-2.6 1-2-3.5 2-2v-2l-2-2 2-3.5 2.6 1 2-.9z M13 11.5a3 3 0 1 0-6 0 3 3 0 0 0 6 0",
  help: "M10 2a8 8 0 1 0 0 16 8 8 0 0 0 0-16 M7.5 7a2.5 2.5 0 1 1 3.5 2.3c-1 .5-1 1-1 2 M10 14v.1",
  bell: "M4 14l1-2V7a5 5 0 0 1 10 0v5l1 2z M8 17h4",
  person: "M10 2a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7 M3 18v-2c0-6 14-6 14 0v2",
  attach:
    "M7 11l6-6a2 2 0 0 1 3 3L8 16a3.5 3.5 0 0 1-5-5l8-8a5 5 0 0 1 7 7l-8 8",
  file: "M4 2h8l4 4v12H4z M12 2v5h4 M7 11h6 M7 14h6",
  star: "M10 2l2.4 5 5.6.8-4 4 1 5.7-5-2.7-5 2.7 1-5.7-4-4L7.6 7z",
  undo: "M7 3L2 8l5 5 M2 8h9a5 5 0 0 1 0 10H8",
  download: "M10 2v11 M6 9l4 4 4-4 M3 15v3h14v-3",
};

export default function MailIcon({
  name,
  size = 20,
}: {
  name: MailIconName;
  size?: number;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth={name === "more" ? 3 : 1.2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name]} />
    </svg>
  );
}
