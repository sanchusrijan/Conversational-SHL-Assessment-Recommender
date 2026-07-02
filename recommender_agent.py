import json
import os
import re
import traceback
import logging
from typing import List, Dict, Any, Optional
import httpx
from anthropic import AsyncAnthropic
from pydantic_models import ChatResponse, RecommendationItem
from catalog_manager import CatalogManager

logger = logging.getLogger(__name__)

class RecommenderAgent:
    def __init__(self, catalog_manager: CatalogManager):
        self.catalog_manager = catalog_manager
        self.anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
        self.client = None
        if self.anthropic_key and self.anthropic_key != "MOCK_KEY":
            self.client = AsyncAnthropic(api_key=self.anthropic_key)
            
        self.gemini_key = os.environ.get("GEMINI_API_KEY")
        self.gemini_model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

    def _extract_active_recommendations(self, messages: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        active = []
        for msg in reversed(messages):
            if msg.get("role") == "assistant":
                urls = re.findall(r'https://www.shl.com/products/product-catalog/view/[a-zA-Z0-9\-_]+/?', msg.get("content", ""))
                if urls:
                    for url in urls:
                        prod = self.catalog_manager.get_product_by_url(url.strip())
                        if prod and prod not in active:
                            active.append(prod)
                    break
        return active

    def _extract_comparison_queries(self, messages: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        found = []
        if not messages:
            return found
            
        last_user_msg = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_user_msg = msg.get("content", "")
                break
                
        last_user_lower = last_user_msg.lower()
        for prod in self.catalog_manager.products:
            prod_name_lower = prod["name"].lower()
            if len(prod_name_lower) > 3 and prod_name_lower in last_user_lower:
                if prod not in found:
                    found.append(prod)
        return found

    def _build_system_prompt(self, candidates: List[Dict[str, Any]], active_list: List[Dict[str, Any]], turn_count: int) -> str:
        candidates_str = ""
        for idx, prod in enumerate(candidates, 1):
            candidates_str += f"[{idx}] NAME: {prod['name']}\n"
            candidates_str += f"    URL: {prod['link']}\n"
            candidates_str += f"    TEST_TYPE: {prod['test_type']}\n"
            candidates_str += f"    KEYS: {', '.join(prod['keys'])}\n"
            candidates_str += f"    DURATION: {prod['duration']}\n"
            candidates_str += f"    LANGUAGES: {', '.join(prod['languages'])}\n"
            candidates_str += f"    DESCRIPTION: {prod['description']}\n\n"

        active_list_str = ""
        if active_list:
            active_list_str = "\n".join([f"- {p['name']} ({p['link']})" for p in active_list])
        else:
            active_list_str = "None"

        prompt = f"""You are the SHL Conversational Assessment Recommender agent. Your task is to guide the user (a recruiter or hiring manager) to a shortlist of 1 to 10 grounded SHL assessments through multi-turn dialogue.

---
### Available Candidate Products in SHL Catalog (Search Results):
These are the ONLY valid products you can recommend. Do NOT recommend any product not in this list:
{candidates_str}
---

### Active Recommendation Shortlist (from previous turns):
{active_list_str}

### Current Conversation Status:
- Total Messages in History: {turn_count} (Note: Both user and assistant messages count towards the 8-turn limit).

---
### Core Behavioral Guidelines:

1. **Clarify (Vague queries)**:
   - If the user's requirements are too vague (e.g. missing role details, seniority, skills, context), do NOT make any recommendations yet. Instead, ask a clarifying question.
   - Example: On Turn 1, if a user says "I need an assessment for hiring", you must clarify (ask who it is for, job level, etc.) and return empty `recommendations: []`.

2. **Recommend**:
   - Once you have sufficient context (role, seniority, specific skills, etc.), retrieve matching products from the candidate list and recommend them.
   - Return between 1 and 10 products.
   - Your `reply` MUST display these recommendations as a markdown table using the exact format:
     | # | Name | Test Type | Keys | Duration | Languages | URL |
     |---|------|-----------|------|----------|-----------|-----|
     | 1 | Product Name | Test Type Code | Product Keys | Duration | Languages | <Product URL> |
     Ensure URLs in the table are enclosed in angle brackets, like `<https://www.shl.com/...>`.
   - The names, URLs, and test types MUST match the candidate list exactly.

3. **Refine**:
   - If the user adds or changes constraints mid-conversation (e.g. "add a cognitive test", "remove personality", "make it Spanish"), update the active shortlist accordingly.
   - Do NOT discard prior constraints. Maintain the active shortlist and modify it based on the new requirements.

4. **Compare**:
   - If the user asks you to compare assessments, answer using only the details (descriptions, durations, keys, languages) of those products from the candidate list. Do not use external training knowledge.

5. **Refuse (Scope Enforcement)**:
   - You only discuss SHL assessments.
   - Refuse off-topic requests (e.g. cooking, coding help, non-SHL topics), general legal compliance questions (e.g. "are we legally required to test", "does this satisfy HIPAA laws"), or general hiring advice.
   - If refusing, return `recommendations: []`, set `end_of_conversation: false` (unless turn cap is reached), and provide a polite refusal message in `reply`.

6. **Turn Cap Handling (CRITICAL)**:
   - If the total messages in history is 6 or more, we are nearing the 8-turn budget limit.
   - You MUST skip any further clarification. You MUST commit to a best-effort recommendation shortlist of 1-10 assessments from the candidate list, present them in the markdown table, and set `end_of_conversation: true`.

---
### Response Format Guidelines:
You must respond with a single, valid JSON object matching the schema below. Do NOT wrap it in markdown code blocks (like ```json), and do not output any extra text.

```json
{{
  "reply": "Your natural language response to the user, including the markdown table if recommendations are committed.",
  "recommendations": [
    {{
      "name": "Exact Name of Assessment from Candidate list",
      "url": "Exact URL of Assessment from Candidate list",
      "test_type": "Exact test_type code from Candidate list"
    }}
  ],
  "end_of_conversation": true/false
}}
```

- When recommending: `recommendations` list must contain 1-10 products, and the markdown table must be in the `reply`.
- When clarifying/refusing: `recommendations` list must be `[]` (empty), and NO markdown table in `reply`.
- Set `end_of_conversation: true` ONLY when the user is satisfied and you've committed to a shortlist, or if you've reached the turn cap limit.
"""
        return prompt

    async def _call_gemini_api(self, system_prompt: str, messages: List[Dict[str, str]], api_key: str) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.gemini_model}:generateContent?key={api_key}"
        
        contents = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            contents.append({
                "role": role,
                "parts": [{"text": msg["content"]}]
            })
            
        payload = {
            "systemInstruction": {
                "parts": [{"text": system_prompt}]
            },
            "contents": contents,
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.0
            }
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, timeout=30.0)
            response.raise_for_status()
            result = response.json()
            try:
                text = result["candidates"][0]["content"]["parts"][0]["text"]
                return text.strip()
            except (KeyError, IndexError) as err:
                raise ValueError(f"Failed to parse text from Gemini response structure: {result}. Error: {err}")

    async def _call_claude_api(self, system_prompt: str, messages: List[Dict[str, str]]) -> str:
        if not self.client:
            raise ValueError("Anthropic client is not initialized. Please verify ANTHROPIC_API_KEY.")
            
        claude_messages = [{"role": msg["role"], "content": msg["content"]} for msg in messages]
        
        response = await self.client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=4000,
            system=system_prompt,
            messages=claude_messages,
            temperature=0.0
        )
        return response.content[0].text.strip()

    async def process_chat(self, messages: List[Dict[str, str]]) -> ChatResponse:
        turn_count = len(messages)
        
        active_list = self._extract_active_recommendations(messages)
        
        user_queries = [msg["content"] for msg in messages if msg.get("role") == "user"]
        combined_query = " ".join(user_queries[-2:]) if user_queries else ""
        
        candidates = self.catalog_manager.search(combined_query, limit=25)
        
        candidate_urls = {p["link"].lower().strip() for p in candidates}
        for act_prod in active_list:
            if act_prod["link"].lower().strip() not in candidate_urls:
                candidates.append(act_prod)
                
        comp_prods = self._extract_comparison_queries(messages)
        for comp_prod in comp_prods:
            if comp_prod["link"].lower().strip() not in candidate_urls:
                candidates.append(comp_prod)

        system_prompt = self._build_system_prompt(candidates, active_list, turn_count)
        
        has_gemini = bool(self.gemini_key)
        has_claude = self.anthropic_key and self.anthropic_key != "MOCK_KEY"
        
        if not has_gemini and not has_claude:
            logger.warning("No API keys found. Falling back to offline mock response.")
            return self._generate_stub_response(messages, active_list, turn_count)

        max_attempts = 3
        current_attempt = 0
        error_context = ""

        while current_attempt < max_attempts:
            try:
                system_with_retry = system_prompt
                if error_context:
                    system_with_retry += f"\n\nWARNING: Your previous response caused validation errors: {error_context}. Please correct your output and return strict JSON matching the schema."

                if has_gemini:
                    logger.info(f"Invoking Gemini API ({self.gemini_model}) via HTTP...")
                    content_text = await self._call_gemini_api(system_with_retry, messages, self.gemini_key)
                else:
                    logger.info("Invoking Anthropic Claude API...")
                    content_text = await self._call_claude_api(system_with_retry, messages)
                
                if content_text.startswith("```"):
                    content_text = re.sub(r'^```(?:json)?\n|```$', '', content_text, flags=re.MULTILINE).strip()
                
                json_data = json.loads(content_text)
                chat_res = ChatResponse.model_validate(json_data)
                
                verified_recs = []
                for rec in chat_res.recommendations:
                    matched = self.catalog_manager.get_product_by_url(rec.url)
                    if not matched:
                        matched = self.catalog_manager.get_product_by_name(rec.name)
                    if matched:
                        verified_recs.append(RecommendationItem(
                            name=matched["name"],
                            url=matched["link"],
                            test_type=matched["test_type"]
                        ))
                chat_res.recommendations = verified_recs
                
                return chat_res
                
            except Exception as e:
                current_attempt += 1
                error_context = f"Error during attempt {current_attempt}: {str(e)}"
                logger.error(f"Validation attempt {current_attempt} failed: {e}")
                
        return ChatResponse(
            reply="I encountered an issue processing your request. Please try again.",
            recommendations=[],
            end_of_conversation=False
        )

    def _generate_stub_response(self, messages: List[Dict[str, str]], active_list: List[Dict[str, Any]], turn_count: int) -> ChatResponse:
        last_msg = messages[-1]["content"].lower() if messages else ""
        
        if "senior leadership" in last_msg or "cxo" in last_msg:
            if "selection" in last_msg:
                recs = [
                    self.catalog_manager.get_product_by_name("Occupational Personality Questionnaire OPQ32r"),
                    self.catalog_manager.get_product_by_name("OPQ Universal Competency Report 2.0"),
                    self.catalog_manager.get_product_by_name("OPQ Leadership Report")
                ]
                recs = [r for r in recs if r]
                return ChatResponse(
                    reply="Shortlist committed.",
                    recommendations=[RecommendationItem(name=r["name"], url=r["link"], test_type=r["test_type"]) for r in recs],
                    end_of_conversation=True
                )
            else:
                return ChatResponse(
                    reply="Happy to narrow that down. Who is this meant for?",
                    recommendations=[],
                    end_of_conversation=False
                )
        return ChatResponse(
            reply="Offline stub response. Set ANTHROPIC_API_KEY or GEMINI_API_KEY environment variable to enable live responses.",
            recommendations=[],
            end_of_conversation=False
        )
