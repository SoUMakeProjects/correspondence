import { useSyncExternalStore } from "react";
import type { Dispatch, SetStateAction } from "react";
import type { Folder, MailPreferences, SavedDraft } from "./mailboxData";

const key = "mailbox.workspace.v2";
type MailboxState = {
  version: 2;
  sessionId: string;
  threadIds: string[];
  selectedThread: string | null;
  folder: Folder;
  metadata: Record<string, MailPreferences>;
  drafts: SavedDraft[];
  draftsSeeded: boolean;
  draftId: string | null;
  composing: boolean;
  selectedId: string | null;
  collapsed: string[];
  storageError: string;
  /** Last shared workspace reset this mailbox has applied (null: not yet known). */
  resetGeneration: string | null;
};
function empty(): MailboxState {
  return {
    version: 2,
    sessionId: crypto.randomUUID(),
    threadIds: [],
    selectedThread: null,
    folder: "inbox",
    metadata: {},
    drafts: [],
    draftsSeeded: false,
    draftId: null,
    composing: false,
    selectedId: null,
    collapsed: [],
    storageError: "",
    resetGeneration: null,
  };
}
function restore(raw: string | null): MailboxState | null {
  try {
    const saved = JSON.parse(raw ?? "null");
    return saved?.version === 2 &&
      typeof saved.sessionId === "string" &&
      Array.isArray(saved.threadIds) &&
      Array.isArray(saved.drafts) &&
      saved.metadata &&
      typeof saved.draftsSeeded === "boolean"
      ? { ...empty(), ...saved, storageError: "" }
      : null;
  } catch {
    return null;
  }
}
let current: MailboxState | undefined;
let serialized: string | null = null;
const listeners = new Set<() => void>();
function snapshot() {
  if (!current) {
    try {
      serialized = localStorage.getItem(key);
    } catch {
      /* Save reports unavailable storage. */
    }
    current = restore(serialized) ?? empty();
  }
  return current;
}
function publish(next: MailboxState) {
  current = { ...next, storageError: "" };
  try {
    const encoded = JSON.stringify(current);
    localStorage.setItem(key, encoded);
    serialized = encoded;
  } catch {
    current = {
      ...current,
      storageError:
        "Browser storage is unavailable. Keep this tab open to avoid losing unsaved mailbox changes.",
    };
  }
  listeners.forEach((listener) => listener());
}
function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
// Reset in another tab also cancels its earlier mailbox session. Late callbacks
// cannot reconnect conversations that the presenter has explicitly cleared.
window.addEventListener("storage", (event) => {
  if (event.key !== key) return;
  serialized = event.newValue;
  current = restore(event.newValue) ?? empty();
  listeners.forEach((listener) => listener());
});
export function updateMailbox(
  sessionId: string,
  change: (state: MailboxState) => MailboxState,
) {
  snapshot();
  try {
    const latest = localStorage.getItem(key);
    if (latest !== serialized) {
      serialized = latest;
      current = restore(latest) ?? current;
    }
  } catch {
    /* Preserve in-memory work if storage becomes unavailable. */
  }
  const previous = snapshot();
  if (previous.sessionId !== sessionId) return;
  const next = change(previous);
  if (next !== previous) publish(next);
}
/** Clears this mailbox. `generation` records which shared workspace reset it matches. */
export function resetMailbox(generation: string | null = null) {
  publish({ ...empty(), resetGeneration: generation });
}
/** Records the shared reset generation without clearing (first contact). */
export function adoptResetGeneration(generation: string) {
  const state = snapshot();
  if (state.resetGeneration === null)
    publish({ ...state, resetGeneration: generation });
}
export function useMailboxState() {
  return useSyncExternalStore(subscribe, snapshot);
}
export function useMailboxField<K extends keyof MailboxState>(
  field: K,
): [MailboxState[K], Dispatch<SetStateAction<MailboxState[K]>>] {
  const state = useMailboxState();
  return [
    state[field],
    (value) =>
      updateMailbox(state.sessionId, (previous) => ({
        ...previous,
        [field]:
          typeof value === "function"
            ? (value as (old: MailboxState[K]) => MailboxState[K])(
                previous[field],
              )
            : value,
      })),
  ];
}
