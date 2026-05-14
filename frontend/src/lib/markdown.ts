import DOMPurify from "dompurify";
import { marked } from "marked";

/**
 * Render a markdown string to sanitized HTML.
 *
 * We trust nothing about the markdown source — `marked` parses the
 * structure, then DOMPurify scrubs the resulting HTML. Inline scripts,
 * `javascript:` URLs, and unknown tags are dropped.
 */
export function renderMarkdown(source: string): string {
  if (!source) return "";
  const raw = marked.parse(source, { async: false, breaks: true }) as string;
  return DOMPurify.sanitize(raw, {
    USE_PROFILES: { html: true },
  });
}
