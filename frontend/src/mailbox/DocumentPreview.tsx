import { useEffect, useRef, useState } from "react";
import MailIcon from "./MailIcon";
import PdfPreview from "./PdfPreview";

export default function DocumentPreview({
  title,
  url,
  onClose,
}: {
  title: string;
  url: string;
  onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [file, setFile] = useState<{ url: string; type: string } | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    setError("");
    setFile(null);
    dialog.current?.showModal();
    const controller = new AbortController();
    let objectUrl = "";
    async function read() {
      try {
        const response = await fetch(url, { signal: controller.signal });
        if (!response.ok) {
          const detail = await response.json().catch(() => null);
          throw new Error(
            detail?.error?.message ??
              (response.status === 404
                ? "This attachment is unavailable. Try again or reopen the message."
                : "The document service could not open this file. Please try again."),
          );
        }
        const type =
          response.headers
            .get("content-type")
            ?.split(";")[0]
            .trim()
            .toLowerCase() ?? "";
        if (
          ![
            "application/pdf",
            "image/png",
            "image/jpeg",
            "image/gif",
            "image/webp",
          ].includes(type)
        )
          throw new Error("This attachment is not a supported PDF or image.");
        const blob = await response.blob();
        if (controller.signal.aborted) return;
        objectUrl = URL.createObjectURL(blob);
        setFile({ url: objectUrl, type });
      } catch (reason) {
        if (!controller.signal.aborted)
          setError(
            reason instanceof Error ? reason.message : "Document unavailable.",
          );
      }
    }
    void read();
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [url, attempt]);
  return (
    <dialog
      ref={dialog}
      className="mail-document-preview"
      aria-labelledby="document-preview-title"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === dialog.current) onClose();
      }}
    >
      <header>
        <MailIcon name="file" size={22} />
        <h2 id="document-preview-title">{title}</h2>
        {file && (
          <a
            href={file.url}
            download={
              /\.(pdf|png|jpe?g|gif|webp)$/i.test(title)
                ? title
                : title +
                  (file.type === "application/pdf"
                    ? ".pdf"
                    : "." + file.type.split("/")[1])
            }
          >
            Download
          </a>
        )}
        <button
          type="button"
          className="mail-icon-button"
          aria-label="Close document preview"
          onClick={onClose}
          autoFocus
        >
          <MailIcon name="close" />
        </button>
      </header>
      {error ? (
        <div className="mail-preview-error">
          <p role="alert">{error}</p>
          <button
            className="mail-tool"
            onClick={() => setAttempt((value) => value + 1)}
          >
            Try again
          </button>
        </div>
      ) : !file ? (
        <p role="status">Opening document…</p>
      ) : file.type.startsWith("image/") ? (
        <div className="mail-image-preview">
          <img
            src={file.url}
            alt={title}
            onError={() =>
              setError("This image could not be opened. Please try again.")
            }
          />
        </div>
      ) : (
        <PdfPreview url={file.url} />
      )}
    </dialog>
  );
}
