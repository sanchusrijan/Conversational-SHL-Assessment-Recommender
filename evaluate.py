import os

# Load local .env file if it exists
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

import re
import json
import asyncio
from typing import List, Dict, Any, Tuple
from catalog_manager import CatalogManager
from recommender_agent import RecommenderAgent
from pydantic_models import ChatResponse

TRACES_DIR = "/Users/sasikala/Desktop/SHL/GenAI_SampleConversations 2"

def parse_trace_file(filepath: str) -> List[Tuple[str, List[str], bool]]:
    """
    Parses a markdown trace file.
    Returns a list of turns.
    Each turn is a Tuple: (user_input, expected_recommendation_names, expected_end_of_conversation)
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Split the file by turns (e.g., "### Turn 1", "### Turn 2", etc.)
    turns_raw = re.split(r'###\s*Turn\s*\d+', content)[1:]
    
    turns = []
    for turn_raw in turns_raw:
        # Extract User message
        user_match = re.search(r'\*\*User\*\*\s*\n+\s*>\s*(.*?)(?=\n+\s*\*\*Agent\*\*|\n+\s*_No recommendations|\n+\s*_`end_of_conversation`|$)', turn_raw, re.DOTALL)
        if not user_match:
            continue
        user_text = user_match.group(1).strip()
        # Clean up blockquote markers in multi-line JDs
        user_text = re.sub(r'^>\s*', '', user_text, flags=re.MULTILINE).strip()
        user_text = user_text.replace("\r", "")
        
        # Extract Expected recommendations from table
        expected_recs = []
        table_rows = re.findall(r'^\|\s*\d+\s*\|([^|]+)\|', turn_raw, re.MULTILINE)
        for row in table_rows:
            name = row.strip()
            # Clean up formatting anomalies in names
            name = name.replace("\n", " ").replace("\r", " ")
            name = re.sub(r'\s+', ' ', name).strip()
            if name != "Name":  # ignore header
                expected_recs.append(name)
                
        # Extract Expected end_of_conversation
        end_match = re.search(r'_`end_of_conversation`:\s*\*\*(true|false)\*\*', turn_raw, re.IGNORECASE)
        expected_end = False
        if end_match:
            expected_end = end_match.group(1).lower() == "true"
            
        turns.append((user_text, expected_recs, expected_end))
        
    return turns

async def run_evaluation():
    catalog_manager = CatalogManager()
    agent = RecommenderAgent(catalog_manager)
    
    # Check if API Key is configured
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    gemini_key = os.environ.get("GEMINI_API_KEY")
    is_mock = (not anthropic_key or anthropic_key == "MOCK_KEY") and not gemini_key
    
    if is_mock:
        print("="*60)
        print("WARNING: Running evaluation in OFFLINE MOCK mode.")
        print("To run live evaluation, set the ANTHROPIC_API_KEY or GEMINI_API_KEY environment variable.")
        print("="*60)

    trace_files = sorted([f for f in os.listdir(TRACES_DIR) if f.endswith(".md")])
    
    total_turns_tested = 0
    total_turns_passed = 0
    
    overall_recall_numerator = 0
    overall_recall_denominator = 0

    for filename in trace_files:
        filepath = os.path.join(TRACES_DIR, filename)
        turns = parse_trace_file(filepath)
        
        print(f"\nEvaluating trace: {filename} ({len(turns)} turns)...")
        
        # Reconstruct chat history as we progress through turns
        chat_history = []
        
        for turn_idx, (user_text, expected_recs, expected_end) in enumerate(turns, 1):
            total_turns_tested += 1
            
            # Append current user input
            chat_history.append({"role": "user", "content": user_text})
            
            # Run the agent
            try:
                # Add delay if using Gemini key to respect the 15 RPM free tier limit (1 request every 5 seconds)
                if os.environ.get("GEMINI_API_KEY"):
                    await asyncio.sleep(5.1)
                agent_res: ChatResponse = await agent.process_chat(chat_history)
            except Exception as e:
                print(f"  [FAIL] Turn {turn_idx}: Exception crashed agent: {e}")
                continue
                
            # Verify recommendations matching
            actual_recs = [rec.name for rec in agent_res.recommendations]
            
            # Print turn results
            expected_set = set(expected_recs)
            actual_set = set(actual_recs)
            
            # Calculate Recall
            recall = 1.0
            if expected_set:
                intersect = expected_set.intersection(actual_set)
                recall = len(intersect) / len(expected_set)
                overall_recall_numerator += len(intersect)
                overall_recall_denominator += len(expected_set)
            else:
                if not actual_set:
                    recall = 1.0
                else:
                    recall = 0.0 # Recommended when trace expected none
            
            # Check correctness of recommendations and end_of_conversation flag
            # Wait, in mock mode, it's expected to only pass on implemented mocks
            recs_correct = (expected_set == actual_set)
            end_correct = (expected_end == agent_res.end_of_conversation)
            
            if recs_correct and end_correct:
                total_turns_passed += 1
                print(f"  [PASS] Turn {turn_idx}: Expected {len(expected_recs)} recs, got {len(actual_recs)} recs. End correct: {agent_res.end_of_conversation}")
            else:
                print(f"  [FAIL] Turn {turn_idx}:")
                print(f"         User prompt: {repr(user_text)}")
                print(f"         Expected: {expected_recs} (End: {expected_end})")
                print(f"         Actual:   {actual_recs} (End: {agent_res.end_of_conversation})")
                
            # Append agent response to history for subsequent turns
            chat_history.append({"role": "assistant", "content": agent_res.reply})
            
    print("\n" + "="*50)
    print("Evaluation Summary:")
    print(f"Total Turns Run:    {total_turns_tested}")
    print(f"Total Turns Passed: {total_turns_passed} ({total_turns_passed / total_turns_tested * 100:.1f}%)")
    if overall_recall_denominator > 0:
        recall_at_10 = overall_recall_numerator / overall_recall_denominator
        print(f"Overall Recall@10:  {recall_at_10 * 100:.1f}%")
    else:
        print("Overall Recall@10:  N/A")
    print("="*50)

if __name__ == "__main__":
    asyncio.run(run_evaluation())
