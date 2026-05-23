"""
LenAI — Production Media Inference API Platform.

Run with Docker Compose:
    cp .env.example .env
    docker compose up -d

For local development (requires running DB/Redis/MinIO):
    cd api && uvicorn app.main:app --reload --port 8000
"""

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.app.main:app", host="0.0.0.0", port=8000, reload=True)
