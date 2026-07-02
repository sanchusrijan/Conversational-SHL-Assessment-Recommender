FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and catalogs
COPY main.py .
COPY pydantic_models.py .
COPY catalog_manager.py .
COPY recommender_agent.py .
COPY shl_product_catalog.json .
COPY trace_recommendations.json .

# Expose port
EXPOSE 8000

# Start FastAPI application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
