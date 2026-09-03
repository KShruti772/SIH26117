import { DocumentInfo } from "../api/rag";

export interface GenerationIntentResult {
  isGeneration: boolean;
  documentId?: string;
  sourceFilename?: string;
  format: "pdf" | "docx";
  title: string;
  topic: string;
  error?: string;
}

/**
 * Recognizes document-generation intents such as:
 * - "generate a summary document of sih2026ppt.pdf"
 * - "create a summary report from sih2026ppt.pdf"
 * - "generate a report from sih2026ppt.pdf"
 * - "export a summary of sih2026ppt.pdf"
 * - "create a PDF summary of sih2026ppt.pdf"
 * - "create a DOCX summary of sih2026ppt.pdf"
 * 
 * Accurately extracts target document reference, format, and title,
 * and validates against the real list of indexed documents.
 */
export function parseGenerationIntent(
  query: string,
  availableDocs: DocumentInfo[] = [],
  selectedDocId?: string | null
): GenerationIntentResult {
  const cleanQuery = (query || "").trim();
  const qLower = cleanQuery.toLowerCase();

  // 1. Generation Intent Pattern Matching
  const generationPatterns = [
    /\b(?:generate|create|export|produce|compile|build|make)\s+(?:an?\s+)?(?:[a-z0-9_-]+\s+)?(?:summary\s+)?(?:document|report|pdf|docx|doc|brief)\b/i,
    /\b(?:generate|create|export|produce|compile|build|make)\s+(?:a\s+)?(?:pdf|docx|word)\s+(?:summary|report|document|brief)\b/i,
    /\b(?:generate|create|export)\s+(?:a\s+)?(?:summary\s+)?(?:report|document|pdf|docx)\s+(?:of|from|for|on|about)\b/i,
    /\b(?:export|download)\s+(?:a\s+)?summary\s+(?:of|from|for|on|about)\b/i,
    /\b(?:generate|create)\s+summary\s+(?:of|from|for)\s+[a-z0-9_\-\.]+\.(?:pdf|docx|txt|doc)\b/i
  ];

  const isGenIntent = generationPatterns.some((pattern) => pattern.test(cleanQuery));

  if (!isGenIntent) {
    return {
      isGeneration: false,
      format: "pdf",
      title: "",
      topic: cleanQuery
    };
  }

  // 2. Format Extraction
  const isDocx = /\b(?:docx|word|doc)\b/i.test(cleanQuery);
  const format: "pdf" | "docx" = isDocx ? "docx" : "pdf";

  // 3. Document Extraction & Resolution
  let resolvedDoc: DocumentInfo | null = null;
  let explicitlyMentionedName: string | null = null;

  // A. Check if an explicit filename with extension is in the query (e.g. "sih2026ppt.pdf", "unknown.docx")
  const fileWithExtMatch = cleanQuery.match(/\b([a-zA-Z0-9_\-\.]+\.(?:pdf|docx|txt|doc|csv|md))\b/i);
  if (fileWithExtMatch) {
    explicitlyMentionedName = fileWithExtMatch[1];
  } else {
    // Check for "of <docname>", "from <docname>", "for <docname>"
    const targetClauseMatch = cleanQuery.match(/(?:of|from|for|on|about)\s+([a-zA-Z0-9_\-\.]+?)(?:\s+(?:as|in)\s+(?:a\s+)?(?:pdf|docx|word))?$/i);
    if (targetClauseMatch) {
      const candidate = targetClauseMatch[1].trim();
      if (candidate && !["the", "this", "all", "selected", "document", "pdf", "file"].includes(candidate.toLowerCase())) {
        explicitlyMentionedName = candidate;
      }
    }
  }

  // B. Attempt matching against availableDocs
  if (explicitlyMentionedName) {
    const targetLower = explicitlyMentionedName.toLowerCase();
    const targetBase = targetLower.replace(/\.[a-z0-9]+$/i, "");

    // Find match in available docs
    const match = availableDocs.find((d) => {
      const dName = (d.filename || "").toLowerCase();
      const dOrig = ((d as any).original_filename || "").toLowerCase();
      const dBase = dName.replace(/\.[a-z0-9]+$/i, "");
      return (
        dName === targetLower ||
        dOrig === targetLower ||
        (targetBase.length > 2 && dBase === targetBase) ||
        dName.includes(targetLower) ||
        targetLower.includes(dName)
      );
    });

    if (match) {
      resolvedDoc = match;
    } else {
      // User explicitly requested a document that does not exist in indexed knowledge base
      return {
        isGeneration: true,
        format,
        title: "",
        topic: cleanQuery,
        error: `Document '${explicitlyMentionedName}' was not found among your indexed documents.`
      };
    }
  }

  // C. Fallback to Selected Document in UI if no explicit document was mentioned in text
  if (!resolvedDoc && selectedDocId) {
    const match = availableDocs.find((d) => d.id === selectedDocId || d.filename === selectedDocId);
    if (match) {
      resolvedDoc = match;
    }
  }

  // D. Fallback if exactly 1 document is in the system
  if (!resolvedDoc && availableDocs.length === 1) {
    resolvedDoc = availableDocs[0];
  }

  // E. If no documents exist in the system
  if (!resolvedDoc && availableDocs.length === 0) {
    return {
      isGeneration: true,
      format,
      title: "",
      topic: cleanQuery,
      error: "No indexed documents available to generate a report."
    };
  }

  // 4. Derive Report Title
  const docTitle = resolvedDoc ? resolvedDoc.filename : "Organizational Knowledge";
  const title = `Summary Report - ${docTitle}`;

  return {
    isGeneration: true,
    documentId: resolvedDoc ? resolvedDoc.id : undefined,
    sourceFilename: resolvedDoc ? resolvedDoc.filename : undefined,
    format,
    title,
    topic: cleanQuery
  };
}
