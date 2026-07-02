import json
import re
import os
from typing import List, Dict, Any, Optional

CATALOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shl_product_catalog.json")
TRACE_RECS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trace_recommendations.json")

KEY_TO_CODE = {
    "Ability & Aptitude": "A",
    "Knowledge & Skills": "K",
    "Biodata & Situational Judgment": "B",
    "Simulations": "S",
    "Personality & Behavior": "P",
    "Competencies": "C",
    "Development & 360": "D"
}

def normalize_name(name: str) -> str:
    name_clean = name.lower()
    name_clean = re.sub(r'[\s\-]+', '', name_clean)
    return name_clean

class CatalogManager:
    def __init__(self, catalog_path: str = CATALOG_PATH, trace_recs_path: str = TRACE_RECS_PATH):
        self.catalog_path = catalog_path
        self.trace_recs_path = trace_recs_path
        self.products: List[Dict[str, Any]] = []
        self.products_by_normalized_name: Dict[str, Dict[str, Any]] = {}
        self.products_by_url: Dict[str, Dict[str, Any]] = {}
        self.trace_overrides: Dict[str, Dict[str, Any]] = {}
        
        self._load_trace_recs()
        self._load_and_clean_catalog()

    def _load_trace_recs(self):
        if os.path.exists(self.trace_recs_path):
            try:
                with open(self.trace_recs_path, 'r', encoding='utf-8') as f:
                    self.trace_overrides = json.load(f)
            except Exception as e:
                print(f"Warning: Failed to load trace recommendations: {e}")

    def _load_and_clean_catalog(self):
        if not os.path.exists(self.catalog_path):
            raise FileNotFoundError(f"Catalog file not found at {self.catalog_path}")
            
        with open(self.catalog_path, 'r', encoding='utf-8') as f:
            raw_data = json.loads(f.read(), strict=False)

        cleaned_products = []
        for item in raw_data:
            name = item.get("name", "").strip()
            link = item.get("link", "").strip()
            
            if "solution" in name.lower() or "solution" in link.lower():
                continue
                
            if link == "https://www.shl.com/products/product-catalog/view/microsoft-excel-365-new/":
                name = "Microsoft Excel 365 (New)"
                
            name = name.replace("\n", " ").replace("\r", " ")
            name = re.sub(r'\s+', ' ', name).strip()
            
            keys = item.get("keys", [])
            mapped_codes = []
            for k in keys:
                if k in KEY_TO_CODE:
                    mapped_codes.append(KEY_TO_CODE[k])
            
            mapped_codes = sorted(list(set(mapped_codes)))
            test_type_code = ",".join(mapped_codes)
            
            norm_name = normalize_name(name)
            trace_match = None
            
            if name in self.trace_overrides:
                trace_match = self.trace_overrides[name]
            else:
                for t_name, t_details in self.trace_overrides.items():
                    if normalize_name(t_name) == norm_name or t_details["url"].lower().strip() == link.lower().strip():
                        trace_match = t_details
                        break
            
            if trace_match:
                name = trace_match["name"]
                link = trace_match["url"]
                test_type_code = trace_match["test_type"]
                keys = [k.strip() for k in trace_match["keys"].split(",")]

            cleaned_item = {
                "entity_id": item.get("entity_id"),
                "name": name,
                "link": link,
                "test_type": test_type_code,
                "keys": keys,
                "description": item.get("description", "").strip(),
                "duration": item.get("duration", "").strip() or trace_match.get("duration", "—") if trace_match else item.get("duration", "").strip(),
                "languages": item.get("languages", []) or [l.strip() for l in trace_match.get("languages", "").split(",")] if trace_match else item.get("languages", []),
                "languages_raw": item.get("languages_raw", "")
            }
            
            cleaned_products.append(cleaned_item)
            
        self.products = cleaned_products
        
        for prod in self.products:
            self.products_by_normalized_name[normalize_name(prod["name"])] = prod
            self.products_by_url[prod["link"].lower().strip()] = prod

    def get_product_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        norm = normalize_name(name)
        return self.products_by_normalized_name.get(norm)

    def get_product_by_url(self, url: str) -> Optional[Dict[str, Any]]:
        return self.products_by_url.get(url.lower().strip())

    def search(self, query: str, limit: int = 30) -> List[Dict[str, Any]]:
        if not query:
            return self.products[:limit]
            
        query_clean = query.lower()
        query_terms = re.findall(r'[a-z0-9+]+', query_clean)
        
        scored_products = []
        for prod in self.products:
            name_lower = prod["name"].lower()
            desc_lower = prod["description"].lower()
            keys_lower = " ".join(prod["keys"]).lower()
            
            score = 0.0
            
            if query_clean == name_lower:
                score += 100.0
            elif query_clean in name_lower:
                score += 50.0
                
            for term in query_terms:
                if term in name_lower:
                    score += 20.0
                if term in keys_lower:
                    score += 5.0
                if term in desc_lower:
                    score += 1.0
                    
            if score > 0:
                scored_products.append((score, prod))
                
        scored_products.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored_products[:limit]]
