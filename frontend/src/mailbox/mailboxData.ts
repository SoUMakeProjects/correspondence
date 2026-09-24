import type { MailUpload, ThreadDetail } from "../api/client";

export type Folder =
  "inbox" | "sent" | "drafts" | "deleted" | "junk" | "archive" | "flagged";
export type MailPreferences = {
  folder?: Exclude<Folder, "drafts" | "flagged">;
  read?: boolean;
  flagged?: boolean;
  pinned?: boolean;
};
export type MailItem = {
  id: string;
  threadId: string;
  subject: string;
  date: string;
  sender: string;
  recipient: string;
  body: string;
  emphasis?: unknown;
  incoming: boolean;
  attachments: Record<string, unknown>[];
};
export type SavedDraft = {
  uploads?: MailUpload[];
  excludedAttachmentKeys?: string[];
  id: string;
  sender?: string;
  subject?: string;
  body?: string;
  templateKey: string;
  threadId: string | null;
  requestId: string;
  savedAt: string;
};

export function readSaved<T>(key: string, fallback: T): T {
  try {
    return JSON.parse(localStorage.getItem(key) ?? "null") ?? fallback;
  } catch {
    return fallback;
  }
}
export function save(key: string, value: unknown) {
  localStorage.setItem(key, JSON.stringify(value));
}
export function messagesFor(conversation: ThreadDetail): MailItem[] {
  return [
    ...conversation.messages.map((message) => ({
      id: message.id,
      threadId: message.thread_id,
      subject: message.subject,
      date: message.created_at,
      sender: message.sender,
      recipient: message.recipient,
      body: message.body,
      attachments: message.attachments,
      incoming: false,
    })),
    ...conversation.deliveries.map((delivery) => {
      const content = delivery.sent_content as Record<string, unknown>;
      return {
        id: String(delivery.id),
        threadId: conversation.thread.id,
        subject: String(content.subject ?? conversation.thread.subject),
        date: String(delivery.created_at),
        sender: String(content.sender),
        recipient: String(content.recipient),
        body: String(content.body),
        emphasis: content.emphasis,
        attachments: (content.attachments as Record<string, unknown>[]) ?? [],
        incoming: true,
      };
    }),
  ].sort((a, b) => a.date.localeCompare(b.date));
}
export function person(address: string) {
  if (/correspondence|servicing|support/i.test(address.split("@")[0]))
    return "Servicing team";
  return address
    .split("@")[0]
    .split(/[._-]/)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}
export function initials(address: string) {
  return person(address)
    .split(" ")
    .slice(0, 2)
    .map((part) => part[0])
    .join("");
}
export function mailDate(value: string, full = false) {
  return new Date(value).toLocaleString("en-US", {
    timeZone: "America/New_York",
    ...(full
      ? ({
          weekday: "short",
          month: "numeric",
          day: "numeric",
          year: "numeric",
        } as const)
      : ({ month: "short", day: "numeric" } as const)),
    hour: "numeric",
    minute: "2-digit",
  });
}
export function dateGroup(value: string) {
  const format = (date: Date) =>
    date.toLocaleDateString("en-US", {
      timeZone: "America/New_York",
      month: "long",
      day: "numeric",
      year: "numeric",
    });
  const today = new Date();
  if (format(new Date(value)) === format(today)) return "Today";
  today.setDate(today.getDate() - 1);
  return format(new Date(value)) === format(today)
    ? "Yesterday"
    : format(new Date(value));
}
