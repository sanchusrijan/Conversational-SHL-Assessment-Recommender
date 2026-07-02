# SHL Conversational Assessment Recommender

An AI-powered conversational agent backend built with FastAPI. It guides recruiters from vague hiring intents (e.g. *"I need a senior Java developer who can work with stakeholders"*) into a grounded shortlist of real SHL assessments within an 8-turn limit.

---

## 📂 Project Structure

* **`main.py`**: FastAPI server hosting `GET /health` and stateless `POST /chat`.
* **`pydantic_models.py`**: Request/response validation schemas.
* **`catalog_manager.py`**: Excludes job solutions, cleans naming anomalies, and provides a lightweight, local search engine over the SHL catalog.
* **`recommender_agent.py`**: Conversational agent logic, intent routing, constraint tracking, turn-cap enforcement, and LLM self-correction retry loops.
* **`evaluate.py`**: Automated local test harness that replays all 10 conversation traces end-to-end to verify correctness.
* **`Dockerfile`** & **`requirements.txt`**: Containerization setup for production deployment.
* **`shl_product_catalog.json`**: Ground truth catalog of individual SHL test solutions.
* **`trace_recommendations.json`**: Ground truth mappings for tests recommended in the conversation traces.

---

## ⚙️ Local Setup

1. **Create and activate a virtual environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure API Credentials**:
   Create a file named `.env` in the root of this project and specify either your Google Gemini or Anthropic Claude API key:
   ```env
   # To use Gemini (defaults to gemini-2.5-flash)
   GEMINI_API_KEY=your-gemini-api-key-here
   
   # Or to use Claude
   # ANTHROPIC_API_KEY=your-claude-api-key-here
   ```

---

## 🧪 Running Locally

### 1. Run the Evaluation Suite
Replays all 10 sample traces and validates agent responses:
```bash
python evaluate.py
```
*(Note: If using a Gemini Free Tier key, a 5-second delay is automatically applied between requests to respect the 15 requests-per-minute rate limit).*

### 2. Start the API Server
Starts the FastAPI application locally:
```bash
uvicorn main:app --reload
```
You can access the health check endpoint at `http://localhost:8000/health`.

---

## 🚀 Deployment

The project is packaged for containerized deployment. 

1. Ensure the platform (e.g. Render, Railway, or Fly) is configured to build from the **`Dockerfile`**.
2. Expose port `8000` (FastAPI default).
3. Set the environment variable:
   * **`ANTHROPIC_API_KEY`** (for Claude deployments) OR
   * **`GEMINI_API_KEY`** (for Gemini deployments)
