const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

// Pure JavaScript replica of parseGenerationIntent for node --test runner
function parseGenerationIntent(query, availableDocs = [], selectedDocId = null) {
  const cleanQuery = (query || "").trim();

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

  const isDocx = /\b(?:docx|word|doc)\b/i.test(cleanQuery);
  const format = isDocx ? "docx" : "pdf";

  let resolvedDoc = null;
  let explicitlyMentionedName = null;

  const fileWithExtMatch = cleanQuery.match(/\b([a-zA-Z0-9_\-\.]+\.(?:pdf|docx|txt|doc|csv|md))\b/i);
  if (fileWithExtMatch) {
    explicitlyMentionedName = fileWithExtMatch[1];
  } else {
    const targetClauseMatch = cleanQuery.match(/(?:of|from|for|on|about)\s+([a-zA-Z0-9_\-\.]+?)(?:\s+(?:as|in)\s+(?:a\s+)?(?:pdf|docx|word))?$/i);
    if (targetClauseMatch) {
      const candidate = targetClauseMatch[1].trim();
      if (candidate && !["the", "this", "all", "selected", "document", "pdf", "file"].includes(candidate.toLowerCase())) {
        explicitlyMentionedName = candidate;
      }
    }
  }

  if (explicitlyMentionedName) {
    const targetLower = explicitlyMentionedName.toLowerCase();
    const targetBase = targetLower.replace(/\.[a-z0-9]+$/i, "");

    const match = availableDocs.find((d) => {
      const dName = (d.filename || "").toLowerCase();
      const dOrig = ((d.original_filename) || "").toLowerCase();
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
      return {
        isGeneration: true,
        format,
        title: "",
        topic: cleanQuery,
        error: `Document '${explicitlyMentionedName}' was not found among your indexed documents.`
      };
    }
  }

  if (!resolvedDoc && selectedDocId) {
    const match = availableDocs.find((d) => d.id === selectedDocId || d.filename === selectedDocId);
    if (match) {
      resolvedDoc = match;
    }
  }

  if (!resolvedDoc && availableDocs.length === 1) {
    resolvedDoc = availableDocs[0];
  }

  if (!resolvedDoc && availableDocs.length === 0) {
    return {
      isGeneration: true,
      format,
      title: "",
      topic: cleanQuery,
      error: "No indexed documents available to generate a report."
    };
  }

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

// Sample mock indexed documents
const sampleDocs = [
  { id: "doc-sih-1", filename: "sih2026ppt.pdf", chunk_count: 8 },
  { id: "doc-safety-2", filename: "Mangalore_Safety_Spec.pdf", chunk_count: 14 }
];

// ==========================================
// TEST SCENARIOS
// ==========================================

test("Knowledge Base Routing - Normal question uses standard QA path", () => {
  const result = parseGenerationIntent("What is the proposed solution?", sampleDocs);
  assert.strictEqual(result.isGeneration, false);
  assert.strictEqual(result.error, undefined);
});

test("Knowledge Base Routing - 'generate a summary document of sih2026ppt.pdf' routes to generation", () => {
  const result = parseGenerationIntent("generate a summary document of sih2026ppt.pdf", sampleDocs);
  assert.strictEqual(result.isGeneration, true);
  assert.strictEqual(result.documentId, "doc-sih-1");
  assert.strictEqual(result.sourceFilename, "sih2026ppt.pdf");
  assert.strictEqual(result.format, "pdf");
  assert.strictEqual(result.error, undefined);
});

test("Knowledge Base Routing - 'create a summary report from sih2026ppt.pdf' routes to generation", () => {
  const result = parseGenerationIntent("create a summary report from sih2026ppt.pdf", sampleDocs);
  assert.strictEqual(result.isGeneration, true);
  assert.strictEqual(result.documentId, "doc-sih-1");
  assert.strictEqual(result.format, "pdf");
});

test("Knowledge Base Routing - 'create a DOCX summary of sih2026ppt.pdf' extracts docx format", () => {
  const result = parseGenerationIntent("create a DOCX summary of sih2026ppt.pdf", sampleDocs);
  assert.strictEqual(result.isGeneration, true);
  assert.strictEqual(result.documentId, "doc-sih-1");
  assert.strictEqual(result.format, "docx");
});

test("Knowledge Base Routing - 'create a PDF summary of sih2026ppt.pdf' extracts pdf format", () => {
  const result = parseGenerationIntent("create a PDF summary of sih2026ppt.pdf", sampleDocs);
  assert.strictEqual(result.isGeneration, true);
  assert.strictEqual(result.documentId, "doc-sih-1");
  assert.strictEqual(result.format, "pdf");
});

test("Knowledge Base Routing - 'export a summary of sih2026ppt.pdf' routes to generation", () => {
  const result = parseGenerationIntent("export a summary of sih2026ppt.pdf", sampleDocs);
  assert.strictEqual(result.isGeneration, true);
  assert.strictEqual(result.documentId, "doc-sih-1");
});

test("Knowledge Base Routing - Unknown document returns clear error message", () => {
  const result = parseGenerationIntent("generate a summary document of non_existent_doc.pdf", sampleDocs);
  assert.strictEqual(result.isGeneration, true);
  assert.strictEqual(result.error, "Document 'non_existent_doc.pdf' was not found among your indexed documents.");
});

test("Knowledge Base Routing - Fallback to selected scoped document when not named in prompt", () => {
  const result = parseGenerationIntent("generate a summary document", sampleDocs, "doc-safety-2");
  assert.strictEqual(result.isGeneration, true);
  assert.strictEqual(result.documentId, "doc-safety-2");
  assert.strictEqual(result.sourceFilename, "Mangalore_Safety_Spec.pdf");
});

test("Ant Design Deprecations - DocumentsView does not use deprecated valueStyle", () => {
  const fileContent = fs.readFileSync(
    path.join(__dirname, "../components/views/DocumentsView.tsx"),
    "utf-8"
  );
  assert.strictEqual(fileContent.includes("valueStyle="), false, "DocumentsView must not use deprecated valueStyle.");
  assert.strictEqual(fileContent.includes("styles={{ content:"), true, "DocumentsView must use styles={{ content: ... }}");
});

test("Ant Design Deprecations - KnowledgeBaseView and DocumentsView do not use deprecated Alert message prop", () => {
  const kbContent = fs.readFileSync(
    path.join(__dirname, "../components/views/KnowledgeBaseView.tsx"),
    "utf-8"
  );
  const docContent = fs.readFileSync(
    path.join(__dirname, "../components/views/DocumentsView.tsx"),
    "utf-8"
  );

  // Check no <Alert ... message=
  assert.strictEqual(/<Alert[^>]*\bmessage=/g.test(kbContent), false, "KnowledgeBaseView must use title instead of message on Alert.");
  assert.strictEqual(/<Alert[^>]*\bmessage=/g.test(docContent), false, "DocumentsView must use title instead of message on Alert.");
});
