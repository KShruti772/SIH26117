"use client";

import React from "react";
import { Cpu, Database } from "lucide-react";
import type { DocumentInfo } from "../../../lib/api/rag";
import type { ModelProfile } from "../../../lib/api/models";
import Button from "../../ui/Button";

interface AssistantContextPanelProps {
  documents: DocumentInfo[];
  currentModel: ModelProfile | null;
  isAdmin: boolean;
  onOpenDocuments: () => void;
  onOpenModels: () => void;
}

export default function AssistantContextPanel({
  documents,
  currentModel,
  isAdmin,
  onOpenDocuments,
  onOpenModels,
}: AssistantContextPanelProps) {
  const document = documents[0];
  const modelName = currentModel?.display_name || currentModel?.model_id;
  const pageCount = document?.pages ?? document?.page_count;
  const chunkCount = document?.chunk_count ?? document?.chunks;

  return (
    <aside className="aegis-assistant-context lg:col-span-2" aria-label="Conversation context">
      <section className="aegis-assistant-context-section">
        <div className="aegis-assistant-context-heading">
          <Database className="h-4 w-4 text-indigo-400" />
          <h2>Context</h2>
        </div>

        {document ? (
          <details>
            <summary>
              <span className="truncate" title={document.filename}>{document.filename}</span>
              {document.status && <span className="aegis-technical-metadata">{document.status}</span>}
            </summary>
            <div className="aegis-assistant-context-details">
              {pageCount != null && <span>Pages <strong>{pageCount}</strong></span>}
              {chunkCount != null && <span>Chunks <strong>{chunkCount}</strong></span>}
              {documents.length > 1 && <span>{documents.length - 1} additional authorized document{documents.length === 2 ? "" : "s"}</span>}
            </div>
          </details>
        ) : (
          <div className="space-y-2">
            <p className="aegis-secondary-copy">No authorized documents available.</p>
            <Button variant="ghost" onClick={onOpenDocuments} className="px-0">Open documents</Button>
          </div>
        )}
      </section>

      <section className="aegis-assistant-context-section">
        <div className="aegis-assistant-context-heading">
          <Cpu className="h-4 w-4 text-blue-400" />
          <h2>Model</h2>
        </div>
        {modelName ? (
          <div className="space-y-2">
            <p className="aegis-assistant-model-name" title={modelName}>{modelName}</p>
            <p className="aegis-secondary-copy">Active local model</p>
          </div>
        ) : (
          <p className="aegis-secondary-copy">No active model reported by runtime.</p>
        )}
        {isAdmin && <Button variant="ghost" onClick={onOpenModels} className="px-0 mt-2">Manage models</Button>}
      </section>
    </aside>
  );
}
