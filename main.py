import os
import logging

if os.path.exists(".env"):
    try:
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ[key.strip()] = val.strip().strip('"').strip("'")
    except Exception as e:
        print(f"Warning: Failed to load .env file: {e}")

from fastapi import FastAPI, HTTPException
from pydantic_models import ChatRequest, ChatResponse
from catalog_manager import CatalogManager
from recommender_agent import RecommenderAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="SHL Conversational Assessment Recommender",
    description="Stateless recommender API for SHL assessments based on candidate catalog search.",
    version="1.0.0"
)

try:
    logger.info("Initializing Catalog Manager...")
    catalog_manager = CatalogManager()
    logger.info("Initializing Recommender Agent...")
    agent = RecommenderAgent(catalog_manager)
    logger.info("Startup complete.")
except Exception as e:
    logger.error(f"Failed to initialize server components: {e}")
    raise e

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    try:
        messages_list = [{"role": msg.role, "content": msg.content} for msg in request.messages]
        
        if not messages_list:
            return ChatResponse(
                reply="Hello! I can help you find the right SHL assessments for your hiring needs. What role or skills are you hiring for?",
                recommendations=[],
                end_of_conversation=False
            )
            
        logger.info(f"Processing chat request with {len(messages_list)} messages...")
        chat_response = await agent.process_chat(messages_list)
        return chat_response
        
    except Exception as e:
        logger.error(f"Error processing chat: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"An internal error occurred: {str(e)}"
        )
