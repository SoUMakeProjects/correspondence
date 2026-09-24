import { useEffect, useRef, useState } from "react";
import { api } from "./api/client";
import type {
  MailMessage,
  MailTemplate,
  MailUpload,
  ThreadDetail,
} from "./api/client";
import { displayText, displayValue } from "./presentation";
import MailIcon from "./mailbox/MailIcon";
import DocumentPreview from "./mailbox/DocumentPreview";
import MailMessageCard from "./mailbox/MailMessageCard";
import {
  updateMailbox,
  useMailboxField,
  useMailboxState,
} from "./mailbox/mailboxStore";
import type { MailIconName } from "./mailbox/MailIcon";
import {
  dateGroup,
  initials,
  mailDate,
  messagesFor,
  person,
  readSaved,
  save,
} from "./mailbox/mailboxData";
import type {
  Folder,
  MailItem,
  MailPreferences,
  SavedDraft,
} from "./mailbox/mailboxData";
import "./mailbox/mailbox.css";

const folders: { id: Folder; name: string; icon: MailIconName }[] = [
  { id: "inbox", name: "Inbox", icon: "inbox" },
  { id: "drafts", name: "Drafts", icon: "draft" },
  { id: "sent", name: "Sent Items", icon: "send" },
  { id: "deleted", name: "Deleted Items", icon: "delete" },
  { id: "junk", name: "Junk Email", icon: "report" },
  { id: "archive", name: "Archive", icon: "archive" },
  { id: "flagged", name: "Flagged", icon: "flag" },
];
const serviceAddress = "correspondence@servicing.example.com";

export default function Mailbox({
  conversations,
  selectedThread,
  onSelect,
  templates,
  onSent,
  error,
  loading,
  onReset,
  onRetry,
}: {
  conversations: ThreadDetail[];
  selectedThread: string | null;
  onSelect: (id: string | null, messageId?: string) => void;
  templates: MailTemplate[];
  onSent: (message: MailMessage) => void;
  error: string;
  loading: boolean;
  onReset: () => void;
  onRetry: () => void;
}) {
  const session = useMailboxState();
  const [folder, setFolder] = useMailboxField("folder");
  const [metadata, setMetadata] = useMailboxField("metadata");
  const [drafts, setDrafts] = useMailboxField("drafts");
  const [draftId, setDraftId] = useMailboxField("draftId");
  const draft = drafts.find((item) => item.id === draftId) ?? null;
  const [preview, setPreview] = useState<{ title: string; url: string } | null>(
    null,
  );
  function setDraft(value: SavedDraft | null) {
    setDrafts((previous) =>
      value
        ? previous.some((item) => item.id === value.id)
          ? previous.map((item) => (item.id === value.id ? value : item))
          : [...previous, value]
        : previous.filter((item) => item.id !== draftId),
    );
    setDraftId(value?.id ?? null);
  }
  useEffect(() => {
    const initial = templates.filter((item) => item.kind === "initial");
    if (!initial.length) return;
    updateMailbox(session.sessionId, (previous) =>
      previous.draftsSeeded
        ? previous
        : {
            ...previous,
            draftsSeeded: true,
            drafts: [
              ...initial.map((item) => ({
                id: crypto.randomUUID(),
                templateKey: item.key,
                threadId: null,
                requestId: crypto.randomUUID(),
                savedAt: new Date().toISOString(),
              })),
              ...previous.drafts,
            ],
          },
    );
  }, [templates, session.sessionId]);
  const [composing, setComposing] = useMailboxField("composing");
  const [selectedId, setSelectedId] = useMailboxField("selectedId");
  const [checked, setChecked] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [menu, setMenu] = useState("");
  const [tab, setTab] = useState("Home");
  const [folderPane, setFolderPane] = useState(true);
  const [compact, setCompact] = useState(() =>
    readSaved("mailbox.compact", false),
  );
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [draftFilter, setDraftFilter] = useState<"all" | "attachments">("all");
  const [draftUndo, setDraftUndo] = useState<SavedDraft[] | null>(null);
  const [foldersOpen, setFoldersOpen] = useState(true);
  const [notice, setNotice] = useState("");
  const [toastHeld, setToastHeld] = useState(false);
  const [undo, setUndo] = useState<Record<string, MailPreferences> | null>(
    null,
  );
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const attachmentInput = useRef<HTMLInputElement>(null);
  // Reset is shared with the Correspondence Desk and deletes every case, so
  // both reset entry points ask first.
  const resetDialog = useRef<HTMLDialogElement>(null);
  const [sendError, setSendError] = useState("");
  const [collapsed, setCollapsed] = useMailboxField("collapsed");
  const sending = useRef(false);
  useEffect(() => {
    if (composing) {
      setNotice("");
      setUndo(null);
      setDraftUndo(null);
    }
  }, [composing]);
  // Notices dismiss themselves; an Undo offer stays longer, and hovering or
  // focusing the toast keeps it open until the pointer/focus leaves.
  useEffect(() => {
    if (!notice || toastHeld) return;
    const timer = window.setTimeout(
      () => {
        setNotice("");
        setUndo(null);
        setDraftUndo(null);
      },
      undo || draftUndo ? 8000 : 3500,
    );
    return () => window.clearTimeout(timer);
  }, [notice, undo, draftUndo, toastHeld]);
  useEffect(() => {
    if (!notice) setToastHeld(false);
  }, [notice]);
  useEffect(() => save("mailbox.compact", compact), [compact]);
  useEffect(() => {
    if (!menu) return;
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMenu("");
    };
    addEventListener("keydown", close);
    return () => removeEventListener("keydown", close);
  }, [menu]);
  const allMessages = conversations
    .flatMap(messagesFor)
    .sort((a, b) => Date.parse(a.date) - Date.parse(b.date));
  const mailFolder = (item: MailItem) =>
    metadata[item.id]?.folder ?? (item.incoming ? "inbox" : "sent");
  const isRead = (item: MailItem) => metadata[item.id]?.read ?? !item.incoming;
  const inFolder = (item: MailItem, value: Folder) =>
    value === "flagged"
      ? !!metadata[item.id]?.flagged && mailFolder(item) !== "deleted"
      : mailFolder(item) === value;
  const folderMessages = allMessages.filter((item) => inFolder(item, folder));
  const visible = folderMessages
    .filter(
      (item) =>
        (!unreadOnly || !isRead(item)) &&
        [item.subject, item.sender, item.recipient, item.body]
          .join(" ")
          .toLowerCase()
          .includes(query.trim().toLowerCase()),
    )
    .sort(
      (a, b) =>
        Number(!!metadata[b.id]?.pinned) - Number(!!metadata[a.id]?.pinned) ||
        b.date.localeCompare(a.date),
    );
  const active =
    visible.find((item) => item.id === selectedId) ??
    visible.find((item) => item.threadId === selectedThread) ??
    visible[0];
  const conversation = conversations.find(
    (item) => item.thread.id === active?.threadId,
  );
  const conversationMessages = (
    conversation ? messagesFor(conversation) : []
  ).sort(
    (a, b) =>
      Date.parse(b.date) - Date.parse(a.date) || b.id.localeCompare(a.id),
  );
  const targets =
    folder === "drafts"
      ? []
      : checked.length
        ? checked
        : active
          ? [active.id]
          : [];
  const canReply =
    folder !== "drafts" && !composing && !!conversation?.reply_templates.length;
  const custom = draft?.templateKey === "CUSTOM";
  const template = templates.find((item) => item.key === draft?.templateKey);
  const chosen =
    draft && (custom || template)
      ? {
          sender: draft.sender ?? template?.sender ?? "",
          recipient: serviceAddress,
          subject:
            draft.subject ??
            (draft.threadId ? "Re: " : "") + (template?.subject ?? ""),
          body: draft.body ?? template?.body ?? "",
          attachments: (template?.attachments ?? []).filter(
            (file) => !draft.excludedAttachmentKeys?.includes(String(file.key)),
          ),
        }
      : undefined;
  const draftConversation = conversations.find(
    (item) => item.thread.id === draft?.threadId,
  );
  const options = draft?.threadId
    ? templates.filter(
        (item) =>
          item.kind === "reply" &&
          item.scenario === draftConversation?.thread.template_key,
      )
    : templates.filter((item) => item.kind === "initial");
  const visibleDrafts = drafts.filter((item) => {
    const template = templates.find((t) => t.key === item.templateKey);
    return (
      (draftFilter === "all" ||
        !!item.uploads?.length ||
        !!template?.attachments.some(
          (file) => !item.excludedAttachmentKeys?.includes(String(file.key)),
        )) &&
      [
        item.subject ?? template?.subject,
        item.body ?? template?.body,
        item.sender ?? template?.sender,
      ]
        .join(" ")
        .toLowerCase()
        .includes(query.trim().toLowerCase())
    );
  });
  const draftTargets = checked.length
    ? checked
    : composing && draft
      ? [draft.id]
      : [];
  const selectable = folder === "drafts" ? visibleDrafts : visible;
  function discardDrafts(ids: string[]) {
    const removed = drafts.filter((item) => ids.includes(item.id));
    if (!removed.length || busy) return;
    setDraftUndo(removed);
    setUndo(null);
    updateMailbox(session.sessionId, (state) => ({
      ...state,
      drafts: state.drafts.filter((item) => !ids.includes(item.id)),
      draftId: ids.includes(state.draftId ?? "") ? null : state.draftId,
      composing: ids.includes(state.draftId ?? "") ? false : state.composing,
    }));
    setChecked([]);
    setNotice(
      `${removed.length === 1 ? "Draft" : `${removed.length} drafts`} deleted.`,
    );
  }
  const count = (value: Folder) =>
    value === "drafts"
      ? drafts.length
      : allMessages.filter(
          (item) =>
            inFolder(item, value) && (value !== "inbox" || !isRead(item)),
        ).length;
  const change = (ids: string[], patch: MailPreferences) =>
    setMetadata((previous) => {
      const next = { ...previous };
      for (const id of ids) next[id] = { ...next[id], ...patch };
      return next;
    });
  function selectFolder(value: Folder) {
    setFolder(value);
    setChecked([]);
    setSelectedId(null);
    setQuery("");
    setUnreadOnly(false);
    setDraftFilter("all");
    setMenu("");
    setComposing(false);
    onSelect(null);
  }
  function selectMessage(item: MailItem) {
    setSelectedId(item.id);
    onSelect(item.threadId, item.id);
    change([item.id], { read: true });
    setComposing(false);
  }
  function openMessage(item: MailItem) {
    setFolder(mailFolder(item));
    setQuery("");
    setUnreadOnly(false);
    setChecked([]);
    setMenu("");
    selectMessage(item);
  }
  function move(value: Exclude<Folder, "drafts" | "flagged">, ids = targets) {
    if (!ids.length) return;
    setDraftUndo(null);
    setUndo(Object.fromEntries(ids.map((id) => [id, metadata[id] ?? {}])));
    change(ids, { folder: value });
    setChecked([]);
    setSelectedId(null);
    onSelect(null);
    setMenu("");
    setNotice(
      (ids.length === 1 ? "Message" : ids.length + " messages") +
        " moved to " +
        folders.find((item) => item.id === value)?.name +
        ".",
    );
  }
  function compose(reply = false) {
    if (busy) return;
    setDraft({
      id: crypto.randomUUID(),
      templateKey: reply
        ? (conversation?.reply_templates[0]?.key ?? "")
        : "CUSTOM",
      threadId: reply ? (active?.threadId ?? null) : null,
      requestId: crypto.randomUUID(),
      savedAt: new Date().toISOString(),
    });
    setComposing(true);
    setSendError("");
    setMenu("");
    setTab("Home");
    setChecked([]);
  }
  async function send() {
    if (!chosen || !draft || sending.current) return;
    sending.current = true;
    setBusy(true);
    setSendError("");
    try {
      const message = await api.sendMail({
        request_id: draft.requestId,
        template_key: draft.templateKey,
        thread_id: draft.threadId,
        attachment_ids: (draft.uploads ?? []).map((file) => file.id),
        excluded_attachment_keys: draft.excludedAttachmentKeys ?? [],
        sender: draft.sender ?? (custom ? chosen.sender : undefined),
        subject: draft.subject ?? (custom ? chosen.subject : undefined),
        body: draft.body ?? (custom ? chosen.body : undefined),
      });
      // Persist acceptance and remove the draft together, before a refresh can
      // lose the thread or resend an already accepted message.
      updateMailbox(session.sessionId, (state) => ({
        ...state,
        drafts: state.drafts.filter((item) => item.id !== draft.id),
        draftId: null,
        composing: false,
        folder: "sent",
        selectedId: message.id,
        selectedThread: message.thread_id,
        threadIds: state.threadIds.includes(message.thread_id)
          ? [...state.threadIds]
          : [...state.threadIds, message.thread_id],
        metadata: { ...state.metadata, [message.id]: { read: true } },
      }));
      setQuery("");
      setUnreadOnly(false);
      setChecked([]);
      change([message.id], { read: true });
      onSent(message);
      onSelect(message.thread_id, message.id);
      setNotice("Message sent.");
      setUndo(null);
    } catch (reason) {
      setSendError(
        reason instanceof Error
          ? reason.message
          : "Your message could not be sent. Try again.",
      );
    } finally {
      setBusy(false);
      sending.current = false;
    }
  }
  async function addAttachments(files: File[]) {
    if (!draft || sending.current || !files.length) return;
    if ((draft.uploads?.length ?? 0) + files.length > 5) {
      setSendError("You can add up to 5 files to a message.");
      return;
    }
    for (const file of files) {
      if (
        !/\.(pdf|png|jpe?g|gif|webp)$/i.test(file.name) ||
        (file.type &&
          ![
            "application/pdf",
            "image/png",
            "image/jpeg",
            "image/gif",
            "image/webp",
          ].includes(file.type))
      ) {
        setSendError("Choose a PDF or a PNG, JPEG, GIF or WebP image.");
        return;
      }
      if (file.size > 5 * 1024 * 1024) {
        setSendError("Each attachment must be 5 MB or smaller.");
        return;
      }
    }
    const currentId = draft.id;
    const uploaded: MailUpload[] = [];
    sending.current = true;
    setBusy(true);
    setUploading(true);
    setSendError("");
    try {
      for (const file of files)
        uploaded.push(await api.uploadAttachment(file, crypto.randomUUID()));
    } catch (reason) {
      setSendError(
        reason instanceof Error
          ? reason.message
          : "The attachment could not be added. Try again.",
      );
    } finally {
      if (uploaded.length)
        setDrafts((previous) =>
          previous.map((item) =>
            item.id === currentId
              ? {
                  ...item,
                  uploads: [...(item.uploads ?? []), ...uploaded],
                  requestId: crypto.randomUUID(),
                  savedAt: new Date().toISOString(),
                }
              : item,
          ),
        );
      setBusy(false);
      setUploading(false);
      sending.current = false;
    }
  }
  function closeDraft(discard = false) {
    if (busy) return;
    if (discard) setDraft(null);
    setComposing(false);
    setSendError("");
    setNotice(discard ? "Draft discarded." : "Draft saved.");
    setUndo(null);
  }
  const toggleMenu = (value: string) => setMenu(menu === value ? "" : value);
  function folderButton(value: Folder) {
    const item = folders.find((entry) => entry.id === value)!;
    return (
      <button
        key={value}
        className={"mail-folder " + (folder === value ? "active" : "")}
        aria-current={folder === value ? "page" : undefined}
        onClick={() => selectFolder(value)}
      >
        <MailIcon name={item.icon} size={18} />
        <span>{item.name}</span>
        {!!count(value) && <b>{count(value)}</b>}
      </button>
    );
  }
  const toolDisabled = !targets.length || composing;
  return (
    <div className={"mail-app " + (compact ? "mail-compact" : "")}>
      {menu && (
        <button
          className="mail-menu-dismiss"
          aria-label="Close menu"
          tabIndex={-1}
          onClick={() => setMenu("")}
        />
      )}
      <header className="mail-topbar">
        <div
          className={"mail-menu-anchor " + (menu === "apps" ? "is-open" : "")}
        >
          <IconButton
            icon="apps"
            label="Apps"
            onClick={() => toggleMenu("apps")}
          />
          {menu === "apps" && (
            <div className="mail-popover">
              <strong>Apps</strong>
              <button onClick={() => selectFolder("inbox")}>
                <MailIcon name="mail" />
                Mailbox
              </button>
            </div>
          )}
        </div>
        <a
          className="mail-brand"
          href="/"
          onClick={(event) => {
            event.preventDefault();
            selectFolder("inbox");
          }}
        >
          Mailbox
        </a>
        <div className="mail-search">
          <MailIcon name="search" size={18} />
          <input
            aria-label="Search mail"
            placeholder="Search"
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setChecked([]);
            }}
          />
          {query && (
            <IconButton
              icon="close"
              label="Clear search"
              onClick={() => setQuery("")}
            />
          )}
        </div>
        <div className="mail-top-actions">
          <IconButton
            icon="refresh"
            label="Reset mailbox"
            disabled={busy}
            onClick={() => resetDialog.current?.showModal()}
          />
          <div
            className={
              "mail-menu-anchor " + (menu === "notifications" ? "is-open" : "")
            }
          >
            <IconButton
              icon="bell"
              label="Notifications"
              onClick={() => toggleMenu("notifications")}
            />
            {!!count("inbox") && <span className="mail-notification-dot" />}
            {menu === "notifications" && (
              <div className="mail-popover mail-popover-right mail-notifications">
                <strong>Notifications</strong>
                {allMessages
                  .filter(
                    (item) =>
                      item.incoming &&
                      !isRead(item) &&
                      mailFolder(item) === "inbox",
                  )
                  .slice(-5)
                  .reverse()
                  .map((item) => (
                    <button key={item.id} onClick={() => openMessage(item)}>
                      <MailIcon name="mail" />
                      <span>
                        {item.subject}
                        <small>{mailDate(item.date)}</small>
                      </span>
                    </button>
                  ))}
                {!count("inbox") && <p>You're all caught up.</p>}
              </div>
            )}
          </div>
          <div
            className={
              "mail-menu-anchor " + (menu === "settings" ? "is-open" : "")
            }
          >
            <IconButton
              icon="settings"
              label="Settings"
              onClick={() => toggleMenu("settings")}
            />
            {menu === "settings" && (
              <div className="mail-popover mail-popover-right">
                <strong>Settings</strong>
                <label>
                  <input
                    type="checkbox"
                    checked={compact}
                    onChange={(event) => setCompact(event.target.checked)}
                  />
                  Compact message list
                </label>
                <label>
                  <input
                    type="checkbox"
                    checked={folderPane}
                    onChange={(event) => setFolderPane(event.target.checked)}
                  />
                  Show folder pane
                </label>
                <p>Dates and times use US Eastern time.</p>
              </div>
            )}
          </div>
          <IconButton
            icon="help"
            label="Help"
            onClick={() => setTab(tab === "Help" ? "Home" : "Help")}
          />
          <div
            className={
              "mail-menu-anchor " + (menu === "account" ? "is-open" : "")
            }
          >
            <button
              className="mail-account"
              aria-label="Mailbox account"
              onClick={() => toggleMenu("account")}
            >
              MB
            </button>
            {menu === "account" && (
              <div className="mail-popover mail-popover-right">
                <strong>Mailbox</strong>
                <p>Requests and replies</p>
                <p>{conversations.length} conversations</p>
              </div>
            )}
          </div>
        </div>
      </header>
      <div className="mail-frame">
        <nav className="mail-app-rail" aria-label="Mailbox shortcuts">
          <IconButton
            icon="mail"
            label="Mail"
            selected
            onClick={() => selectFolder("inbox")}
          />
          <IconButton
            icon="send"
            label="Sent mail"
            onClick={() => selectFolder("sent")}
          />
          <IconButton
            icon="draft"
            label="Draft messages"
            onClick={() => selectFolder("drafts")}
          />
          <IconButton
            icon="flag"
            label="Flagged mail"
            onClick={() => selectFolder("flagged")}
          />
          <span />
          <IconButton
            icon="help"
            label="Mailbox help"
            onClick={() => setTab("Help")}
          />
        </nav>
        <main className="mail-main" aria-label="Mailbox">
          <div className="mail-ribbon-tabs">
            <IconButton
              icon="menu"
              label="Toggle folder pane"
              onClick={() => setFolderPane(!folderPane)}
            />
            <div role="tablist" aria-label="Mailbox ribbon">
              {["Home", "View", "Help"].map((value) => (
                <button
                  role="tab"
                  aria-selected={tab === value}
                  key={value}
                  onClick={() => {
                    setTab(value);
                    setMenu("");
                  }}
                >
                  {value}
                </button>
              ))}
            </div>
            {(error || loading) && (
              <span className="mail-connection">
                {error ? "Connection interrupted" : "Updating…"}
              </span>
            )}
          </div>
          <div
            className="mail-toolbar"
            role="toolbar"
            aria-label="Mail actions"
          >
            {tab === "Home" ? (
              <>
                <button
                  className="mail-new"
                  onClick={() => compose()}
                  disabled={!templates.length || busy}
                >
                  <MailIcon name="mail" size={18} />
                  New mail
                </button>
                <Tool
                  icon="delete"
                  label="Delete"
                  disabled={
                    folder === "drafts"
                      ? !draftTargets.length || busy
                      : toolDisabled || folder === "deleted"
                  }
                  onClick={() =>
                    folder === "drafts"
                      ? discardDrafts(draftTargets)
                      : move("deleted")
                  }
                />
                <Tool
                  icon="archive"
                  label="Archive"
                  disabled={toolDisabled || folder === "archive"}
                  onClick={() => move("archive")}
                />
                <div
                  className={
                    "mail-menu-anchor " + (menu === "report" ? "is-open" : "")
                  }
                >
                  <Tool
                    icon="report"
                    label="Report"
                    dropdown
                    disabled={toolDisabled}
                    onClick={() => toggleMenu("report")}
                  />
                  {menu === "report" && (
                    <div className="mail-popover">
                      <button onClick={() => move("junk")}>
                        <MailIcon name="report" />
                        Mark as junk
                      </button>
                    </div>
                  )}
                </div>
                <div
                  className={
                    "mail-menu-anchor " + (menu === "sweep" ? "is-open" : "")
                  }
                >
                  <Tool
                    icon="sweep"
                    label="Sweep"
                    disabled={toolDisabled}
                    onClick={() => toggleMenu("sweep")}
                  />
                  {menu === "sweep" && active && (
                    <div className="mail-popover">
                      <strong>Messages from {person(active.sender)}</strong>
                      <button
                        onClick={() =>
                          move(
                            "archive",
                            folderMessages
                              .filter((item) => item.sender === active.sender)
                              .map((item) => item.id),
                          )
                        }
                      >
                        Archive all in this folder
                      </button>
                    </div>
                  )}
                </div>
                <div
                  className={
                    "mail-menu-anchor " + (menu === "move" ? "is-open" : "")
                  }
                >
                  <Tool
                    icon="folder"
                    label="Move to"
                    dropdown
                    disabled={toolDisabled}
                    onClick={() => toggleMenu("move")}
                  />
                  {menu === "move" && (
                    <div className="mail-popover">
                      <strong>Move to folder</strong>
                      {folders
                        .filter(
                          (item) => !["drafts", "flagged"].includes(item.id),
                        )
                        .map((item) => (
                          <button
                            key={item.id}
                            onClick={() =>
                              move(
                                item.id as Exclude<
                                  Folder,
                                  "drafts" | "flagged"
                                >,
                              )
                            }
                          >
                            <MailIcon name={item.icon} size={17} />
                            {item.name}
                          </button>
                        ))}
                    </div>
                  )}
                </div>
                <span className="mail-tool-divider" />
                {canReply && (
                  <IconButton
                    icon="reply"
                    label="Reply"
                    className="mail-purple"
                    onClick={() => compose(true)}
                  />
                )}
                {canReply && (
                  <IconButton
                    icon="replyAll"
                    label="Reply all"
                    className="mail-purple"
                    onClick={() => compose(true)}
                  />
                )}
                <Tool
                  icon="read"
                  label="Read / Unread"
                  disabled={toolDisabled}
                  onClick={() =>
                    change(targets, { read: active ? !isRead(active) : true })
                  }
                />
                <IconButton
                  icon="flag"
                  label={
                    active && metadata[active.id]?.flagged ? "Unflag" : "Flag"
                  }
                  className="mail-red"
                  disabled={toolDisabled}
                  onClick={() =>
                    change(targets, {
                      flagged: active ? !metadata[active.id]?.flagged : true,
                    })
                  }
                />
                <IconButton
                  icon="pin"
                  label={
                    active && metadata[active.id]?.pinned ? "Unpin" : "Pin"
                  }
                  className="mail-blue"
                  disabled={toolDisabled}
                  onClick={() =>
                    change(targets, {
                      pinned: active ? !metadata[active.id]?.pinned : true,
                    })
                  }
                />
                <span className="mail-tool-divider" />
                <IconButton
                  icon="print"
                  label="Print conversation"
                  disabled={!active || composing}
                  onClick={() => window.print()}
                />
                <div
                  className={
                    "mail-menu-anchor " + (menu === "more" ? "is-open" : "")
                  }
                >
                  <IconButton
                    icon="more"
                    label="More actions"
                    onClick={() => toggleMenu("more")}
                  />
                  {menu === "more" && (
                    <div className="mail-popover mail-popover-right">
                      <button
                        onClick={() => {
                          change(
                            folderMessages.map((item) => item.id),
                            { read: true },
                          );
                          setMenu("");
                        }}
                      >
                        Mark all as read
                      </button>
                      <button
                        disabled={busy}
                        onClick={() => {
                          setMenu("");
                          resetDialog.current?.showModal();
                        }}
                      >
                        Reset mailbox
                      </button>
                    </div>
                  )}
                </div>
              </>
            ) : tab === "View" ? (
              <>
                <Tool
                  icon="menu"
                  label={folderPane ? "Hide folder pane" : "Show folder pane"}
                  onClick={() => setFolderPane(!folderPane)}
                />
                <Tool
                  icon="filter"
                  label={compact ? "Comfortable spacing" : "Compact spacing"}
                  onClick={() => setCompact(!compact)}
                />
                <Tool
                  icon="read"
                  label={unreadOnly ? "Show all messages" : "Show unread only"}
                  disabled={folder === "drafts"}
                  onClick={() => setUnreadOnly(!unreadOnly)}
                />
              </>
            ) : (
              <div className="mail-help-copy">
                <MailIcon name="help" />
                <span>
                  Open a prepared request in <b>Drafts</b>, or choose{" "}
                  <b>New mail</b> to write your own email. Responses arrive in{" "}
                  <b>Inbox</b>. Open a conversation and choose <b>Reply</b> to
                  follow up.
                </span>
              </div>
            )}
          </div>
          {error && (
            <div className="mail-error" role="alert">
              {error}
              <button onClick={onRetry}>Try again</button>
            </div>
          )}
          <div
            className={"mail-layout " + (folderPane ? "" : "folders-hidden")}
          >
            {folderPane && (
              <aside className="mail-folders" aria-label="Mail folders">
                <button
                  className="mail-folder-heading mail-folders-heading"
                  aria-expanded={foldersOpen}
                  onClick={() => setFoldersOpen(!foldersOpen)}
                >
                  <MailIcon name="chevron" size={13} />
                  Folders
                </button>
                {foldersOpen && (
                  <nav aria-label="Folders">
                    {folders.map((item) => folderButton(item.id))}
                  </nav>
                )}
              </aside>
            )}
            <section
              className="mail-message-list"
              aria-label="Mail conversations"
            >
              <header className="mail-list-heading">
                <h1>
                  {query
                    ? "Search results"
                    : folders.find((item) => item.id === folder)?.name}
                </h1>
                <span />
                <input
                  type="checkbox"
                  aria-label={
                    folder === "drafts"
                      ? "Select all drafts"
                      : "Select all messages"
                  }
                  ref={(element) => {
                    if (element)
                      element.indeterminate =
                        selectable.some((item) => checked.includes(item.id)) &&
                        !selectable.every((item) => checked.includes(item.id));
                  }}
                  checked={
                    !!selectable.length &&
                    selectable.every((item) => checked.includes(item.id))
                  }
                  onChange={(event) =>
                    setChecked(
                      event.target.checked
                        ? selectable.map((item) => item.id)
                        : [],
                    )
                  }
                />
                <div
                  className={
                    "mail-menu-anchor " + (menu === "filter" ? "is-open" : "")
                  }
                >
                  <IconButton
                    icon="filter"
                    label={
                      folder === "drafts" ? "Filter drafts" : "Filter messages"
                    }
                    selected={
                      folder === "drafts" ? draftFilter !== "all" : unreadOnly
                    }
                    onClick={() => toggleMenu("filter")}
                  />
                  {menu === "filter" && (
                    <div className="mail-popover mail-popover-right">
                      {folder === "drafts" ? (
                        <>
                          <button
                            onClick={() => {
                              setDraftFilter("all");
                              setChecked([]);
                              setMenu("");
                            }}
                          >
                            {draftFilter === "all" && (
                              <MailIcon name="check" size={16} />
                            )}
                            All drafts
                          </button>
                          <button
                            onClick={() => {
                              setDraftFilter("attachments");
                              setChecked([]);
                              setMenu("");
                            }}
                          >
                            {draftFilter === "attachments" && (
                              <MailIcon name="check" size={16} />
                            )}
                            With attachments
                          </button>
                        </>
                      ) : (
                        <>
                          <button
                            onClick={() => {
                              setUnreadOnly(false);
                              setChecked([]);
                              setMenu("");
                            }}
                          >
                            {!unreadOnly && <MailIcon name="check" size={16} />}
                            All messages
                          </button>
                          <button
                            onClick={() => {
                              setUnreadOnly(true);
                              setChecked([]);
                              setMenu("");
                            }}
                          >
                            {unreadOnly && <MailIcon name="check" size={16} />}
                            Unread
                          </button>
                        </>
                      )}
                    </div>
                  )}
                </div>
              </header>
              <div className="mail-list-scroll">
                {folder === "drafts" ? (
                  <>
                    {draftFilter !== "all" && (
                      <p className="mail-list-filter">
                        With attachments{" "}
                        <button onClick={() => setDraftFilter("all")}>
                          Clear
                        </button>
                      </p>
                    )}
                    {!!checked.length && (
                      <p className="mail-list-filter">
                        {checked.length} selected{" "}
                        <button onClick={() => setChecked([])}>
                          Clear selection
                        </button>
                      </p>
                    )}
                    {visibleDrafts.map((item) => {
                      const template = templates.find(
                        (t) => t.key === item.templateKey,
                      );
                      const subject =
                        (item.subject ?? template?.subject) || "New message";
                      const attached =
                        !!item.uploads?.length ||
                        !!template?.attachments.some(
                          (file) =>
                            !item.excludedAttachmentKeys?.includes(
                              String(file.key),
                            ),
                        );
                      return (
                        <div
                          key={item.id}
                          className={
                            "mail-draft-row " +
                            (composing && draftId === item.id ? "selected" : "")
                          }
                        >
                          <input
                            type="checkbox"
                            aria-label={"Select draft " + subject}
                            checked={checked.includes(item.id)}
                            onChange={(event) =>
                              setChecked((previous) =>
                                event.target.checked
                                  ? [...previous, item.id]
                                  : previous.filter((id) => id !== item.id),
                              )
                            }
                          />
                          <button
                            className="mail-draft-content"
                            aria-pressed={composing && draftId === item.id}
                            onClick={() => {
                              if (busy) return;
                              setDraftId(item.id);
                              setComposing(true);
                              setSendError("");
                            }}
                          >
                            <strong>{subject}</strong>
                            <span className="mail-draft-sender">
                              {(item.sender ?? template?.sender) ||
                                "Add a sender"}
                            </span>
                            <span className="mail-draft-meta">
                              <time>{mailDate(item.savedAt)}</time>
                              {attached && <MailIcon name="attach" size={14} />}
                            </span>
                          </button>
                        </div>
                      );
                    })}
                    {!visibleDrafts.length && (
                      <div className="mail-list-empty">
                        {drafts.length
                          ? "No matching drafts."
                          : "You have no drafts."}
                      </div>
                    )}
                  </>
                ) : (
                  <>
                    {unreadOnly && (
                      <p className="mail-list-filter">
                        Unread messages{" "}
                        <button onClick={() => setUnreadOnly(false)}>
                          Clear
                        </button>
                      </p>
                    )}
                    {visible.map((item, index) => (
                      <div key={item.id}>
                        {(index === 0 ||
                          dateGroup(visible[index - 1].date) !==
                            dateGroup(item.date)) && (
                          <div className="mail-date-group">
                            {metadata[item.id]?.pinned
                              ? "Pinned"
                              : dateGroup(item.date)}
                          </div>
                        )}
                        <div
                          className={
                            "mail-message-row " +
                            (active?.id === item.id && !composing
                              ? "selected "
                              : "") +
                            (isRead(item) ? "" : "unread")
                          }
                        >
                          <div className="mail-row-select">
                            <span
                              className={
                                "mail-avatar tone-" +
                                (item.incoming ? "blue" : "gray")
                              }
                            >
                              {initials(item.sender)}
                            </span>
                            <input
                              type="checkbox"
                              aria-label={"Select " + item.subject}
                              checked={checked.includes(item.id)}
                              onChange={(event) =>
                                setChecked((previous) =>
                                  event.target.checked
                                    ? [...previous, item.id]
                                    : previous.filter((id) => id !== item.id),
                                )
                              }
                            />
                          </div>
                          <button
                            className="mail-row-content"
                            aria-pressed={active?.id === item.id}
                            onClick={() => selectMessage(item)}
                          >
                            <span className="mail-row-from">
                              {person(item.sender)}
                              <span>
                                {metadata[item.id]?.flagged && (
                                  <MailIcon name="flag" size={13} />
                                )}
                                {metadata[item.id]?.pinned && (
                                  <MailIcon name="pin" size={13} />
                                )}
                                {!!item.attachments.length && (
                                  <MailIcon name="attach" size={13} />
                                )}
                              </span>
                            </span>
                            <span className="mail-row-subject">
                              <span>{item.subject}</span>
                              <time>
                                {new Date(item.date).toLocaleTimeString(
                                  "en-US",
                                  {
                                    timeZone: "America/New_York",
                                    hour: "numeric",
                                    minute: "2-digit",
                                  },
                                )}
                              </time>
                            </span>
                            <span className="mail-row-preview">
                              {displayText(item.body).replace(/\s+/g, " ")}
                            </span>
                          </button>
                        </div>
                      </div>
                    ))}
                    {!visible.length && (
                      <div className="mail-list-empty">
                        <MailIcon name={query ? "search" : "inbox"} size={30} />
                        <p>
                          {loading
                            ? "Loading mail…"
                            : query
                              ? "No results found"
                              : unreadOnly
                                ? "No unread messages"
                                : folder === "inbox"
                                  ? "You're all caught up"
                                  : "This folder is empty"}
                        </p>
                        {(query || folder !== "inbox") && (
                          <small>
                            {query
                              ? "Try a different word or name."
                              : "Messages in this folder appear here."}
                          </small>
                        )}
                      </div>
                    )}
                  </>
                )}
              </div>
            </section>
            <section
              className="mail-reading-pane"
              aria-label={composing ? "Compose message" : "Reading pane"}
            >
              {composing && draft ? (
                <section
                  className="mail-compose"
                  role="dialog"
                  aria-labelledby="compose-title"
                >
                  <header>
                    <h2 id="compose-title">
                      {draft.threadId ? "Reply" : "New message"}
                    </h2>
                    <span>Saved to Drafts</span>
                    <IconButton
                      icon="close"
                      label="Close message"
                      disabled={busy}
                      onClick={() => closeDraft()}
                    />
                  </header>
                  <form
                    onSubmit={(event) => {
                      event.preventDefault();
                      void send();
                    }}
                  >
                    {draft.threadId && options.length > 1 && (
                      <fieldset className="mail-reply-intent">
                        <legend>Payment type</legend>
                        {options.map((option) => (
                          <label key={option.key}>
                            <input
                              type="radio"
                              name="payment-type"
                              checked={draft.templateKey === option.key}
                              disabled={busy}
                              onChange={() =>
                                setDraft({
                                  ...draft,
                                  templateKey: option.key,
                                  body: undefined,
                                  excludedAttachmentKeys: [],
                                  requestId: crypto.randomUUID(),
                                })
                              }
                            />
                            {option.eft_intent === "outgoing_refund"
                              ? "Refund"
                              : option.eft_intent === "incoming_payment"
                                ? "Mortgage payment"
                                : "Line-of-credit draw"}
                          </label>
                        ))}
                      </fieldset>
                    )}
                    {chosen && (
                      <>
                        <label className="mail-compose-address">
                          <span>From</span>
                          <input
                            aria-label="From"
                            autoFocus={custom}
                            type="email"
                            required
                            maxLength={254}
                            value={chosen.sender}
                            disabled={busy}
                            placeholder="name@outlook.com"
                            onChange={(event) =>
                              setDraft({
                                ...draft,
                                sender: event.target.value,
                                requestId: crypto.randomUUID(),
                              })
                            }
                          />
                        </label>
                        <label className="mail-compose-address">
                          <span>To</span>
                          <span className="mail-address-chip">
                            <MailIcon name="mail" size={15} />
                            {serviceAddress}
                          </span>
                        </label>
                        <label className="mail-compose-address mail-subject-field">
                          <span>Subject</span>
                          <input
                            className="mail-compose-subject"
                            aria-label="Message subject"
                            required
                            maxLength={200}
                            placeholder="Add a subject"
                            value={chosen.subject}
                            disabled={busy}
                            onChange={(event) =>
                              setDraft({
                                ...draft,
                                subject: event.target.value,
                                requestId: crypto.randomUUID(),
                              })
                            }
                          />
                        </label>
                        <div className="mail-add-attachments">
                          <button
                            type="button"
                            className="mail-tool"
                            disabled={busy}
                            onClick={() => attachmentInput.current?.click()}
                          >
                            <MailIcon name="attach" size={18} />
                            {uploading ? "Adding files…" : "Add attachment"}
                          </button>
                          <input
                            ref={attachmentInput}
                            className="mail-sr-only"
                            type="file"
                            accept=".pdf,.png,.jpg,.jpeg,.gif,.webp,application/pdf,image/png,image/jpeg,image/gif,image/webp"
                            multiple
                            aria-label="Add attachments"
                            disabled={busy}
                            onChange={(event) => {
                              const files = Array.from(
                                event.target.files ?? [],
                              );
                              event.target.value = "";
                              void addAttachments(files);
                            }}
                          />
                        </div>
                        {(!!chosen.attachments.length ||
                          !!draft.uploads?.length) && (
                          <div className="mail-compose-attachments">
                            {chosen.attachments.map((attachment) => (
                              <div
                                className="mail-upload-chip"
                                key={String(attachment.key)}
                              >
                                <Attachment
                                  attachment={attachment}
                                  onOpen={() =>
                                    setPreview({
                                      title: displayValue(attachment.title),
                                      url: `/api/mail/templates/${encodeURIComponent(draft.templateKey)}/attachments/${encodeURIComponent(String(attachment.key))}`,
                                    })
                                  }
                                />
                                <IconButton
                                  icon="close"
                                  label={
                                    "Remove " + displayValue(attachment.title)
                                  }
                                  disabled={busy}
                                  onClick={() =>
                                    setDraft({
                                      ...draft,
                                      excludedAttachmentKeys: [
                                        ...(draft.excludedAttachmentKeys ?? []),
                                        String(attachment.key),
                                      ],
                                      requestId: crypto.randomUUID(),
                                    })
                                  }
                                />
                              </div>
                            ))}
                            {draft.uploads?.map((file) => (
                              <div className="mail-upload-chip" key={file.id}>
                                <Attachment
                                  attachment={file}
                                  onOpen={() =>
                                    setPreview({
                                      title: file.title,
                                      url: `/api/mail/attachments/${file.id}/file`,
                                    })
                                  }
                                />
                                <IconButton
                                  icon="close"
                                  label={"Remove " + file.title}
                                  disabled={busy}
                                  onClick={() =>
                                    setDraft({
                                      ...draft,
                                      uploads: draft.uploads?.filter(
                                        (item) => item.id !== file.id,
                                      ),
                                      requestId: crypto.randomUUID(),
                                    })
                                  }
                                />
                              </div>
                            ))}
                          </div>
                        )}
                        <textarea
                          aria-label="Message body"
                          value={chosen.body}
                          required
                          maxLength={12000}
                          placeholder="Write your message…"
                          disabled={busy}
                          onChange={(event) =>
                            setDraft({
                              ...draft,
                              body: event.target.value,
                              requestId: crypto.randomUUID(),
                            })
                          }
                        />
                      </>
                    )}
                    {sendError && (
                      <p className="mail-error" role="alert">
                        {sendError}
                      </p>
                    )}
                    <footer>
                      <button
                        className="mail-send-button"
                        aria-label="Send message"
                        disabled={busy || !chosen}
                      >
                        <MailIcon name="send" size={18} />
                        {uploading
                          ? "Adding files…"
                          : busy
                            ? "Sending…"
                            : "Send"}
                      </button>
                      <button
                        type="button"
                        className="mail-tool"
                        disabled={busy}
                        onClick={() => closeDraft(true)}
                      >
                        <MailIcon name="delete" size={18} />
                        Discard
                      </button>
                      <span>All changes saved</span>
                    </footer>
                  </form>
                </section>
              ) : active && folder !== "drafts" ? (
                <>
                  <div className="mail-reading-subject">
                    <h2>{conversation?.thread.subject ?? active.subject}</h2>
                    {metadata[active.id]?.flagged && (
                      <MailIcon name="flag" size={18} />
                    )}
                  </div>
                  <div className="mail-reading-scroll">
                    {conversation?.signals
                      .filter((signal) => signal.status === "blocked")
                      .map((signal) => (
                        <p className="mail-error" role="status" key={signal.id}>
                          {signal.detail}
                        </p>
                      ))}
                    {conversationMessages.map((item) => (
                      <MailMessageCard
                        key={item.id}
                        item={item}
                        collapsed={collapsed.includes(item.id)}
                        onToggle={() =>
                          setCollapsed((previous) =>
                            previous.includes(item.id)
                              ? previous.filter((id) => id !== item.id)
                              : [...previous, item.id],
                          )
                        }
                        onReply={canReply ? () => compose(true) : undefined}
                        onPreview={(title, url) => setPreview({ title, url })}
                      />
                    ))}
                  </div>
                </>
              ) : (
                <div className="mail-reading-empty">
                  <MailIcon name="mail" size={64} />
                  <h2>
                    {folder === "drafts"
                      ? "Your drafts"
                      : "Select an item to read"}
                  </h2>
                  <p>
                    {folder === "drafts"
                      ? "Open a saved draft to continue your message."
                      : "Nothing is selected"}
                  </p>
                </div>
              )}
            </section>
          </div>
        </main>
      </div>
      {preview && (
        <DocumentPreview {...preview} onClose={() => setPreview(null)} />
      )}
      <dialog
        className="mail-confirm-dialog"
        ref={resetDialog}
        aria-labelledby="mail-reset-title"
        onClick={(event) => {
          if (event.target === resetDialog.current) resetDialog.current.close();
        }}
      >
        <header>
          <h2 id="mail-reset-title">Reset mailbox?</h2>
          <button
            className="mail-icon-button"
            aria-label="Close reset dialog"
            onClick={() => resetDialog.current?.close()}
          >
            <MailIcon name="close" size={16} />
          </button>
        </header>
        <div className="mail-confirm-body">
          <p>
            This clears every message in this mailbox and restores the five
            prepared requests in Drafts. It also deletes every case in the
            Correspondence Desk, including its agent activity, drafts and
            documents.
          </p>
          <p className="mail-confirm-hint">This cannot be undone.</p>
        </div>
        <footer>
          <button
            className="mail-tool"
            autoFocus
            onClick={() => resetDialog.current?.close()}
          >
            Cancel
          </button>
          <button
            className="mail-confirm-danger"
            disabled={busy}
            onClick={() => {
              resetDialog.current?.close();
              onReset();
            }}
          >
            Reset mailbox
          </button>
        </footer>
      </dialog>
      {notice && (
        <div
          className="mail-toast"
          role="status"
          onMouseEnter={() => setToastHeld(true)}
          onMouseLeave={() => setToastHeld(false)}
          onFocus={() => setToastHeld(true)}
          onBlur={(event) => {
            if (
              !event.currentTarget.contains(event.relatedTarget as Node | null)
            )
              setToastHeld(false);
          }}
        >
          <MailIcon name="check" size={18} />
          <span>{notice}</span>
          {(undo || draftUndo) && (
            <button
              onClick={() => {
                setMetadata((previous) => {
                  const next = { ...previous };
                  for (const id of Object.keys(undo ?? {})) {
                    next[id] = { ...next[id], folder: undo![id].folder };
                  }
                  return next;
                });
                if (draftUndo)
                  setDrafts((previous) => [
                    ...draftUndo.filter(
                      (item) =>
                        !previous.some((existing) => existing.id === item.id),
                    ),
                    ...previous,
                  ]);
                setUndo(null);
                setDraftUndo(null);
                setNotice(draftUndo ? "Drafts restored." : "Move undone.");
              }}
            >
              Undo
            </button>
          )}
          <IconButton
            icon="close"
            label="Dismiss notification"
            onClick={() => setNotice("")}
          />
        </div>
      )}
    </div>
  );
}

function IconButton({
  icon,
  label,
  onClick,
  disabled = false,
  selected = false,
  className = "",
}: {
  icon: MailIconName;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  selected?: boolean;
  className?: string;
}) {
  return (
    <button
      type="button"
      className={"mail-icon-button " + (selected ? "active " : "") + className}
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
    >
      <MailIcon name={icon} size={18} />
    </button>
  );
}
function Tool({
  icon,
  label,
  onClick,
  disabled = false,
  dropdown = false,
}: {
  icon: MailIconName;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  dropdown?: boolean;
}) {
  return (
    <button
      type="button"
      className="mail-tool"
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
    >
      <MailIcon name={icon} size={18} />
      <span>{label}</span>
      {dropdown && <MailIcon name="chevron" size={11} />}
    </button>
  );
}
function Attachment({
  attachment,
  onOpen,
}: {
  attachment: Record<string, unknown>;
  onOpen: () => void;
}) {
  return (
    <button
      type="button"
      className="mail-attachment"
      onClick={onOpen}
      aria-label={"Preview " + displayValue(attachment.title)}
    >
      <span className="mail-pdf-icon">
        <MailIcon name="file" size={23} />
      </span>
      <span>
        {displayValue(attachment.title)}
        <small>Open document</small>
      </span>
    </button>
  );
}
