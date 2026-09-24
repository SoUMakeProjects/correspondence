import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { ThreadDetail } from "../api/client";
import Mailbox from "../Mailbox";
import { useDeskData } from "./useDeskData";
import {
  adoptResetGeneration,
  resetMailbox,
  updateMailbox,
  useMailboxState,
} from "../mailbox/mailboxStore";

export default function SenderMailboxPage() {
  const session = useMailboxState();
  const [resetError, setResetError] = useState("");
  const resetting = useRef(false);
  // The reset is shared with the Correspondence Desk through the server. When
  // either app resets, the generation changes and this mailbox clears itself.
  const shared = useDeskData(api.resetState, 2000, true);
  const generation = shared.value?.generation;
  const seen = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (!generation || seen.current === generation) return;
    seen.current = generation;
    if (session.resetGeneration === null) adoptResetGeneration(generation);
    else if (session.resetGeneration !== generation) resetMailbox(generation);
  }, [generation]);
  async function onReset() {
    if (resetting.current) return;
    resetting.current = true;
    setResetError("");
    try {
      const state = await api.resetWorkspace();
      seen.current = state.generation;
      resetMailbox(state.generation);
    } catch (reason) {
      setResetError(
        `Reset failed: ${reason instanceof Error ? reason.message : "the server could not be reached"}.`,
      );
    } finally {
      resetting.current = false;
    }
  }
  return (
    <MailboxSession
      key={session.sessionId}
      onReset={() => void onReset()}
      resetError={resetError}
    />
  );
}

function MailboxSession({
  onReset,
  resetError,
}: {
  onReset: () => void;
  resetError: string;
}) {
  const session = useMailboxState();
  const { selectedThread: threadId, threadIds, sessionId } = session;
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    history.replaceState(null, "", "/");
  }, []);
  const read = useCallback(
    async (signal: AbortSignal) => {
      const conversations: ThreadDetail[] = [];
      for (let start = 0; start < threadIds.length; start += 4) {
        conversations.push(
          ...(await Promise.all(
            threadIds
              .slice(start, start + 4)
              .map((id) => api.mailThread(id, signal)),
          )),
        );
      }
      return conversations;
    },
    [threadIds],
  );
  const mailbox = useDeskData(read, 1800, true);
  const readTemplates = useCallback(
    (signal: AbortSignal) => {
      void revision;
      return api.mailTemplates(signal);
    },
    [revision],
  );
  const templates = useDeskData(readTemplates, 10000, true);
  return (
    <Mailbox
      conversations={mailbox.value ?? []}
      selectedThread={threadId}
      onSelect={(selectedThread) =>
        updateMailbox(sessionId, (state) => ({ ...state, selectedThread }))
      }
      templates={templates.value ?? []}
      onSent={(message) =>
        updateMailbox(sessionId, (state) => ({
          ...state,
          threadIds: state.threadIds.includes(message.thread_id)
            ? [...state.threadIds]
            : [...state.threadIds, message.thread_id],
        }))
      }
      error={
        resetError || session.storageError || mailbox.error || templates.error
      }
      loading={!templates.value}
      onReset={onReset}
      onRetry={() => {
        setRevision((value) => value + 1);
        updateMailbox(sessionId, (state) => ({
          ...state,
          threadIds: [...state.threadIds],
        }));
      }}
    />
  );
}
