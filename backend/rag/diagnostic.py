import os
from backend.rag.embeddings import get_local_embedding_model

def run_embedding_diagnostic():
    model_path = os.path.abspath("./models/all-MiniLM-L6-v2")
    if not os.path.exists(model_path):
        print("Embedding provider: LOCAL")
        print("Embedding model: all-MiniLM-L6-v2")
        print("Status: MISSING (Model folder not found)")
        print(f"Model path/cache: {model_path}")
        print("Mock fallback: DISABLED")
        return

    model = get_local_embedding_model(model_path)
    sample_vec = model.embed_query("AEGIS local embedding diagnostic test")

    print("Embedding provider: LOCAL")
    print(f"Embedding model: {model.model_name}")
    print(f"Embedding dimension: {len(sample_vec)}")
    print("Device: CPU")
    print(f"Model path/cache: {model.model_path}")
    print("Mock fallback: DISABLED")

if __name__ == "__main__":
    run_embedding_diagnostic()
