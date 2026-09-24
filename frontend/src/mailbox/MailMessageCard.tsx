import { displayText, displayValue } from "../presentation";
import type { MailItem } from "./mailboxData";
import { initials, mailDate, person } from "./mailboxData";
import MailIcon from "./MailIcon";
import { LetterText } from "../LetterText";

export default function MailMessageCard({
  item,
  collapsed,
  onToggle,
  onReply,
  onPreview,
}: {
  item: MailItem;
  collapsed: boolean;
  onToggle: () => void;
  onReply?: () => void;
  onPreview: (title: string, url: string) => void;
}) {
  return (
    <article
      className={"mail-letter " + (collapsed ? "collapsed" : "")}
      data-message-id={item.id}
      data-direction={item.incoming ? "incoming" : "outgoing"}
    >
      <header className="mail-card-header">
        <button
          className="mail-letter-heading"
          aria-expanded={!collapsed}
          aria-label={`${collapsed ? "Expand" : "Collapse"} message from ${person(item.sender)}`}
          onClick={onToggle}
        >
          <span
            className={"mail-avatar tone-" + (item.incoming ? "blue" : "gray")}
          >
            {initials(item.sender)}
          </span>
          <span className="mail-letter-from">
            <strong title={item.sender}>{person(item.sender)}</strong>
            <span className="mail-sender-address">{item.sender}</span>
            <span className="mail-card-recipient">
              To: <span title={item.recipient}>{person(item.recipient)}</span>
            </span>
          </span>
        </button>
        <div className="mail-card-meta">
          <div className="mail-card-actions">
            {onReply && (
              <>
                <button
                  className="mail-icon-button mail-purple"
                  title="Reply"
                  aria-label={`Reply to ${person(item.sender)}`}
                  onClick={onReply}
                >
                  <MailIcon name="reply" size={20} />
                </button>
                <button
                  className="mail-icon-button mail-purple"
                  title="Reply all"
                  aria-label={`Reply all to ${person(item.sender)}`}
                  onClick={onReply}
                >
                  <MailIcon name="replyAll" size={20} />
                </button>
              </>
            )}
            <button
              className="mail-icon-button mail-card-collapse"
              aria-label={collapsed ? "Expand message" : "Collapse message"}
              aria-expanded={!collapsed}
              onClick={onToggle}
            >
              <MailIcon name="chevron" size={16} />
            </button>
          </div>
          <time dateTime={item.date}>{mailDate(item.date, true)}</time>
        </div>
      </header>
      {collapsed ? (
        <p className="mail-collapsed-preview">
          {displayText(item.body).replace(/\s+/g, " ")}
        </p>
      ) : (
        <div className="mail-letter-content">
          {!!item.attachments.length && (
            <div className="mail-attachments">
              {item.attachments.map((attachment, index) => (
                <button
                  type="button"
                  className="mail-attachment"
                  key={index}
                  aria-label={"Preview " + displayValue(attachment.title)}
                  onClick={() =>
                    onPreview(
                      displayValue(attachment.title),
                      `/api/mail/${item.incoming ? "deliveries" : "messages"}/${item.id}/attachments/${index}`,
                    )
                  }
                >
                  <span className="mail-pdf-icon">
                    <MailIcon name="file" size={24} />
                  </span>
                  <span>
                    {displayValue(attachment.title)}
                    <small>
                      {String(attachment.media_type ?? "").startsWith("image/")
                        ? "Image"
                        : "PDF document"}
                    </small>
                  </span>
                </button>
              ))}
            </div>
          )}
          <div className="mail-letter-body">
            <LetterText body={item.body} emphasis={item.emphasis} />
          </div>
          {onReply && (
            <footer className="mail-card-reply-actions">
              <button
                onClick={onReply}
                aria-label={`Reply to message from ${person(item.sender)}`}
              >
                <MailIcon name="reply" size={20} />
                Reply
              </button>
              <button
                onClick={onReply}
                aria-label={`Reply all to message from ${person(item.sender)}`}
              >
                <MailIcon name="replyAll" size={20} />
                Reply all
              </button>
            </footer>
          )}
        </div>
      )}
    </article>
  );
}
