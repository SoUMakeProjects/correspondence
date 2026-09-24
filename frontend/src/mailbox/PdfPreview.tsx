import { useEffect, useRef, useState } from "react";
import type { PDFDocumentLoadingTask } from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";

export default function PdfPreview({ url }: { url: string }) {
  const container = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState("Opening pages…");
  const [error, setError] = useState("");
  useEffect(() => {
    let cancelled = false;
    let task: PDFDocumentLoadingTask | undefined;
    const pages = container.current!;
    async function render() {
      try {
        const { getDocument, GlobalWorkerOptions } = await import("pdfjs-dist");
        if (cancelled) return;
        GlobalWorkerOptions.workerSrc = workerUrl;
        task = getDocument({
          url,
          useSystemFonts: true,
        });
        const document = await task.promise;
        for (let number = 1; number <= document.numPages; number++) {
          if (cancelled) return;
          const page = await document.getPage(number);
          if (cancelled) return;
          const base = page.getViewport({ scale: 1 });
          const viewport = page.getViewport({
            scale: Math.min(
              1.4,
              Math.max(0.5, (pages.clientWidth - 48) / base.width),
            ),
          });
          const ratio = Math.min(window.devicePixelRatio || 1, 2);
          const canvas = window.document.createElement("canvas");
          canvas.width = Math.ceil(viewport.width * ratio);
          canvas.height = Math.ceil(viewport.height * ratio);
          canvas.style.width = `${viewport.width}px`;
          canvas.style.height = `${viewport.height}px`;
          canvas.setAttribute("role", "img");
          canvas.setAttribute(
            "aria-label",
            `Page ${number} of ${document.numPages}`,
          );
          pages.appendChild(canvas);
          await page.render({
            canvas,
            viewport,
            transform: [ratio, 0, 0, ratio, 0, 0],
          }).promise;
          if (cancelled) return;
          canvas.dataset.rendered = "true";
          setStatus(
            number === document.numPages
              ? ""
              : `Opening page ${number + 1} of ${document.numPages}…`,
          );
        }
      } catch {
        if (!cancelled) {
          setStatus("");
          setError(
            "This PDF could not be displayed. Use Download to open the file.",
          );
        }
      }
    }
    void render();
    return () => {
      cancelled = true;
      void task?.destroy().catch(() => undefined);
      pages.replaceChildren();
    };
  }, [url]);
  return (
    <div className="mail-pdf-viewer">
      {status && <p role="status">{status}</p>}
      {error && <p role="alert">{error}</p>}
      <div
        ref={container}
        className="mail-pdf-pages"
        aria-label="Document pages"
      />
    </div>
  );
}
