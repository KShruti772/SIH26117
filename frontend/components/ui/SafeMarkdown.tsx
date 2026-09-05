"use client";

import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface SafeMarkdownProps {
  content?: string | null;
  className?: string;
}

function isSafeExternalHref(href?: string) {
  if (!href) return false;
  try {
    const url = new URL(href, "https://aegis.local");
    return url.protocol === "https:" || url.protocol === "http:" || url.protocol === "mailto:";
  } catch {
    return false;
  }
}

/** Renders synthesized model output without enabling raw HTML or unsafe URL schemes. */
export default function SafeMarkdown({ content, className }: SafeMarkdownProps) {
  if (!content?.trim()) return null;

  return (
    <div className={`aegis-markdown ${className || ""}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        skipHtml
        components={{
          h1: ({ children }) => <h1>{children}</h1>,
          h2: ({ children }) => <h2>{children}</h2>,
          h3: ({ children }) => <h3>{children}</h3>,
          h4: ({ children }) => <h4>{children}</h4>,
          p: ({ children }) => <p>{children}</p>,
          ul: ({ children }) => <ul>{children}</ul>,
          ol: ({ children }) => <ol>{children}</ol>,
          li: ({ children }) => <li>{children}</li>,
          blockquote: ({ children }) => <blockquote>{children}</blockquote>,
          code: ({ className: codeClassName, children, ...props }) => {
            const language = /language-([\w+-]+)/.exec(codeClassName || "")?.[1];
            const rawValue = String(children);
            const value = rawValue.replace(/\n$/, "");
            const isBlock = Boolean(codeClassName) || rawValue.includes("\n");

            return isBlock ? (
              <div className="aegis-markdown-code-block">
                {language && <div className="aegis-markdown-code-language">{language}</div>}
                <pre><code className={codeClassName} {...props}>{value}</code></pre>
              </div>
            ) : <code {...props}>{children}</code>;
          },
          table: ({ children }) => <div className="aegis-markdown-table-wrap"><table>{children}</table></div>,
          thead: ({ children }) => <thead>{children}</thead>,
          tbody: ({ children }) => <tbody>{children}</tbody>,
          tr: ({ children }) => <tr>{children}</tr>,
          th: ({ children }) => <th scope="col">{children}</th>,
          td: ({ children }) => <td>{children}</td>,
          a: ({ href, children }) => isSafeExternalHref(href)
            ? <a href={href} target="_blank" rel="noreferrer noopener">{children}</a>
            : <span>{children}</span>,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
