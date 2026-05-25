import modal

app = modal.App("lenai-init-qdrant")

@app.function(
    secrets=[modal.Secret.from_name("lenai-db-secret")],
    image=modal.Image.debian_slim(python_version="3.11")
    .pip_install("qdrant-client", "httpx")
)
def init_collection():
    import os
    import httpx
    
    qdrant_url = os.environ["QDRANT_URL"]
    qdrant_api_key = os.environ.get("QDRANT_API_KEY")
    
    headers = {}
    if qdrant_api_key:
        headers["api-key"] = qdrant_api_key
        headers["Authorization"] = f"Bearer {qdrant_api_key}"
        
    print(f"Connecting to Qdrant at {qdrant_url}")
    
    # We will do it via raw HTTP since the qdrant-client might fail
    import json
    
    # Check if collection exists
    collection_name = "clinical_docs"
    
    url = f"{qdrant_url}/collections/{collection_name}"
    req = httpx.get(url, headers=headers)
    print("GET collection:", req.status_code, req.text)
    
    if req.status_code == 404:
        # Create it
        payload = {
            "vectors": {
                "size": 1024, # e5-large dim
                "distance": "Cosine"
            }
        }
        res = httpx.put(url, json=payload, headers=headers)
        print("PUT collection:", res.status_code, res.text)
        
    print("Done!")

@app.local_entrypoint()
def main():
    init_collection.remote()
