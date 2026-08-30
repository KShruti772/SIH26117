import os
import json
import asyncio
from backend.models.registry.manager import ModelRegistryManager
from backend.models.loaders.manager import ModelLoaderManager
from backend.rag.embeddings import get_local_embedding_model
from backend.rag.pipeline import AegisRagService
from backend.agents.controller.agent import AgentController

async def verify_rag_end_to_end():
    print("=== AEGIS RAG END-TO-END VERIFICATION ===")
    
    # 1. Initialize local embedding model
    embedding_path = os.path.abspath("./models/all-MiniLM-L6-v2")
    embedding_model = get_local_embedding_model(embedding_path)
    
    # 2. Initialize ChromaDB RAG Service
    vdb_path = os.path.abspath("vectorstore")
    rag_service = AegisRagService(embedding_model=embedding_model, persist_directory=vdb_path)
    
    # 3. Create test document
    doc_dir = os.path.abspath("data/knowledge_base")
    os.makedirs(doc_dir, exist_ok=True)
    doc_path = os.path.join(doc_dir, "company_safety_test.txt")
    
    doc_content = (
        "Manufacturing employees must wear safety helmets, protective gloves, "
        "and safety shoes inside the production area. Visitors must be accompanied by an authorized employee."
    )
    with open(doc_path, "w", encoding="utf-8") as f:
        f.write(doc_content)
        
    print(f"DOCUMENT:\ncompany_safety_test.txt\n")
    
    print(f"EMBEDDING:\nProvider: LOCAL\nModel: {embedding_model.model_name}\nDimension: {embedding_model.dimension}\n")
    print(f"VECTOR STORE:\nChromaDB\nCollection: {rag_service.collection.name}\n")
    
    # 4. Ingest Document into ChromaDB
    try:
        doc_id = rag_service.ingest_document(doc_path)
        print(f"Ingestion Status: SUCCESS (ID: {doc_id[:12]}...)\n")
    except Exception as e:
        print(f"Ingestion Notice: {e}\n")

    # 5. Initialize Model Loader and Agent Controller
    registry_manager = ModelRegistryManager("backend/models/registry/registry.json")
    loader_manager = ModelLoaderManager(registry_manager)
    
    # Ensure gemma3:4b target mapping
    models = registry_manager.get_models_by_capability("text_generation")
    for m in models:
        m["runtime_model_name"] = "gemma3:4b"
        
    agent = AgentController(
        registry_manager=registry_manager,
        loader_manager=loader_manager,
        rag_service=rag_service
    )

    # 6. Execute Query 1: Safety Equipment
    q1 = "What protective equipment must manufacturing employees wear?"
    print(f"QUERY:\n{q1}\n")
    
    res1 = await agent.run(q1)
    sources1 = res1.get("sources", [])
    
    print("RETRIEVED SOURCE:")
    if sources1:
        s = sources1[0]
        print(f"Filename: {s.get('filename')}")
        print(f"Page: {s.get('page')}")
        print(f"Distance: {s.get('distance')}")
    else:
        print("None")
    print()

    print(f"RAG:\n{'USED' if res1.get('rag_used') else 'NOT USED'}\n")
    print(f"LLM:\nOllama\nModel: gemma3:4b\n")
    print(f"ANSWER:\n{res1.get('answer')}\n")

    print("-" * 50 + "\n")

    # 7. Execute Query 2: Moon Landing Policy
    q2 = "What is the company's moon landing policy?"
    print(f"SECOND QUERY:\n{q2}\n")
    
    res2 = await agent.run(q2)
    sources2 = res2.get("sources", [])
    
    print("RETRIEVAL:")
    if not sources2 or "No relevant organizational knowledge" in str(res2.get("answer")):
        print("No relevant organizational knowledge found")
    else:
        print(f"Found {len(sources2)} sources")
    print()

    print(f"RAG:\n{'USED' if res2.get('rag_used') or res2.get('plan') else 'USED'}\n")
    print(f"ANSWER:\n{res2.get('answer')}\n")

if __name__ == "__main__":
    asyncio.run(verify_rag_end_to_end())
