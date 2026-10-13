"""
Offline Multi-Agent Job: Product Catalogue Enrichment.
Iterates through catalogue models, scrapes/parses product brochures and web pages,
extracts structured technical fields via local LLM, diffs against existing catalogue data,
and generates proposals in data/proposals/ for human approval.
Guarantees:
- Respects rate limit (1.5s delay) and caches raw HTML in data/html_cache/
- Missing fields explicitly remain 'missing'
- Diff conflicts flagged and recorded in proposal
- NEVER modifies data/catalogue_products.json directly
"""

import os
import sys
import json
import time
import logging
import argparse
from pathlib import Path
from typing import Dict, Any, List, Optional
import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from jobs.runner import JobRunner, JobProposal

logger = logging.getLogger("jobs.product_enrichment")

HTML_CACHE_DIR = Path("data/html_cache")
PROPOSALS_DIR = Path("data/proposals")
CATALOGUE_PATH = Path("data/catalogue_products.json")
REPORT_PATH = Path("docs/ENRICHMENT_REPORT.md")


class ProductEnrichmentFields(BaseModel):
    model_id: str
    specs: Dict[str, Any] = Field(default_factory=dict)
    connectivity: List[str] = Field(default_factory=list)
    accessories: List[str] = Field(default_factory=list)
    consumables: List[str] = Field(default_factory=list)
    media_compatibility: List[str] = Field(default_factory=list)
    warranty: str = "missing"
    use_cases: List[str] = Field(default_factory=list)
    best_for: List[str] = Field(default_factory=list)
    not_ideal_for: List[str] = Field(default_factory=list)
    source_urls: Dict[str, str] = Field(default_factory=dict)
    missing_fields: List[str] = Field(default_factory=list)


def extract_text_from_html(html_content: str) -> str:
    soup = BeautifulSoup(html_content, "html.parser")
    # Remove script and style elements
    for script in soup(["script", "style", "noscript", "svg"]):
        script.decompose()
    text = soup.get_text(separator="\n")
    # Clean up excess whitespace
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines[:300])  # Cap context to prevent token explosion


class JobProductEnrichment:
    def __init__(
        self,
        runner: Optional[JobRunner] = None,
        catalogue_path: Path = CATALOGUE_PATH,
        html_cache_dir: Path = HTML_CACHE_DIR,
        rate_limit_seconds: float = 1.5,
    ):
        self.runner = runner or JobRunner(job_name="product_enrichment")
        self.catalogue_path = Path(catalogue_path)
        self.html_cache_dir = Path(html_cache_dir)
        self.html_cache_dir.mkdir(parents=True, exist_ok=True)
        self.rate_limit_seconds = rate_limit_seconds
        self._last_request_time = 0.0

    def load_catalogue(self) -> List[Dict[str, Any]]:
        if not self.catalogue_path.exists():
            logger.error(f"Catalogue file not found at {self.catalogue_path}")
            return []
        with open(self.catalogue_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def fetch_page_content(self, model_id: str, url: Optional[str]) -> tuple[str, str]:
        """
        Retrieves page content from local cache or fetches remotely with rate limiting.
        Returns (content_text, source_url).
        """
        cache_file = self.html_cache_dir / f"{model_id}.html"
        raw_site_file = Path(f"data/raw_site/{model_id}.html")

        if cache_file.exists():
            with open(cache_file, "r", encoding="utf-8") as f:
                return extract_text_from_html(f.read()), f"cache://{cache_file.name}"

        if raw_site_file.exists():
            with open(raw_site_file, "r", encoding="utf-8") as f:
                return extract_text_from_html(f.read()), f"local://{raw_site_file.name}"

        if not url:
            return "", "missing"

        # Rate limiting
        elapsed = time.time() - self._last_request_time
        if elapsed < self.rate_limit_seconds:
            time.sleep(self.rate_limit_seconds - elapsed)

        try:
            headers = {"User-Agent": "KeplerTechSalesAI-EnrichmentBot/1.0 (+http://keplertech.ae)"}
            resp = requests.get(url, headers=headers, timeout=10.0)
            self._last_request_time = time.time()
            if resp.status_code == 200:
                html_text = resp.text
                with open(cache_file, "w", encoding="utf-8") as f:
                    f.write(html_text)
                return extract_text_from_html(html_text), url
        except Exception as e:
            logger.warning(f"Failed to fetch remote URL {url}: {e}")

        return "", "fetch_failed"

    def diff_product_fields(
        self,
        current: Dict[str, Any],
        enriched: ProductEnrichmentFields,
    ) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Compares enriched fields against current product entry.
        Returns (proposed_changes, conflicts).
        """
        proposed: Dict[str, Any] = {}
        conflicts: List[Dict[str, Any]] = []

        # Check specs diff
        for k, v in enriched.specs.items():
            curr_v = current.get(k)
            if curr_v is None or curr_v == "":
                proposed[k] = v
            elif str(curr_v).strip().lower() != str(v).strip().lower():
                conflicts.append({
                    "field": k,
                    "catalogue_value": curr_v,
                    "enriched_value": v,
                    "source": enriched.source_urls.get(k, "source_doc"),
                })

        # Compare best_for & not_ideal_for
        if enriched.best_for and not current.get("best_for"):
            proposed["best_for"] = enriched.best_for
        if enriched.not_ideal_for and not current.get("not_ideal_for"):
            proposed["not_ideal_for"] = enriched.not_ideal_for

        # Compare connectivity & accessories
        if enriched.connectivity and not current.get("connectivity"):
            proposed["connectivity"] = enriched.connectivity
        if enriched.accessories and not current.get("accessories"):
            proposed["accessories"] = enriched.accessories

        # Warranty
        if enriched.warranty != "missing" and not current.get("warranty"):
            proposed["warranty"] = enriched.warranty

        return proposed, conflicts

    def enrich_product(
        self,
        product: Dict[str, Any],
        mock_response: Optional[Dict[str, Any]] = None,
    ) -> Optional[JobProposal]:
        model_id = product.get("id") or product.get("model_family", "unknown")
        url = product.get("product_url")
        content_text, source_url = self.fetch_page_content(model_id, url)

        evidence = {
            "model_id": model_id,
            "display_name": product.get("display_name", ""),
            "catalogue_data": {
                "print_speed": product.get("print_speed"),
                "dpi": product.get("dpi"),
                "memory": product.get("memory"),
                "paper_size": product.get("paper_size"),
            },
            "document_text": content_text or "No external brochure or product page found.",
            "source_url": source_url,
        }

        system_instruction = (
            "You are a technical catalog data enrichment engine for Kepler Tech LLC.\n"
            "Extract verified technical fields from the provided evidence.\n"
            "STRICT RULES:\n"
            "1. ONLY extract attributes documented in the document_text or catalogue_data.\n"
            "2. If an attribute is NOT mentioned, add it to 'missing_fields' and DO NOT guess.\n"
            "3. 'best_for' and 'not_ideal_for' must strictly summarize verified capabilities from text."
        )

        user_prompt = f"Enrich technical specifications and capabilities for model '{model_id}'."

        enriched: ProductEnrichmentFields = self.runner.execute_step(
            step_name=f"enrich_{model_id}",
            system_instruction=system_instruction,
            user_prompt=user_prompt,
            evidence=evidence,
            output_schema=ProductEnrichmentFields,
            mock_response=mock_response,
        )

        proposed_changes, conflicts = self.diff_product_fields(product, enriched)

        if proposed_changes or conflicts:
            proposal = self.runner.save_proposal(
                target_file=str(self.catalogue_path),
                proposed_changes={
                    "model_id": model_id,
                    "updates": proposed_changes,
                },
                conflicts_reported=conflicts,
            )
            return proposal

        return None

    def run(self, limit: int = 5, specific_model_id: Optional[str] = None) -> List[JobProposal]:
        catalogue = self.load_catalogue()
        if specific_model_id:
            catalogue = [p for p in catalogue if p.get("id") == specific_model_id or p.get("model_family") == specific_model_id]
        else:
            catalogue = catalogue[:limit]

        proposals = []
        conflicts_count = 0
        for p in catalogue:
            try:
                prop = self.enrich_product(p)
                if prop:
                    proposals.append(prop)
                    conflicts_count += len(prop.conflicts_reported)
            except Exception as e:
                logger.error(f"Error enriching product {p.get('id')}: {e}")

        self.runner.finalize()

        # Write markdown summary report
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(REPORT_PATH, "w", encoding="utf-8") as f:
            f.write("# Product Enrichment Job Report\n\n")
            f.write(f"- **Run ID:** `{self.runner.run_id}`\n")
            f.write(f"- **Models Evaluated:** {len(catalogue)}\n")
            f.write(f"- **Proposals Generated:** {len(proposals)}\n")
            f.write(f"- **Conflicts Flagged:** {conflicts_count}\n\n")
            f.write("## Generated Proposals\n\n")
            for prop in proposals:
                f.write(f"### Proposal `{prop.proposal_id}`: {prop.proposed_changes.get('model_id')}\n")
                f.write(f"- Proposed Updates: `{json.dumps(prop.proposed_changes.get('updates'))}`\n")
                f.write(f"- Conflicts: {len(prop.conflicts_reported)}\n")
                for c in prop.conflicts_reported:
                    f.write(f"  - `{c.get('field')}`: current='{c.get('catalogue_value')}' vs enriched='{c.get('enriched_value')}'\n")
                f.write("\n")

        logger.info(f"Enrichment report written to {REPORT_PATH}")
        return proposals


def main():
    parser = argparse.ArgumentParser(description="Offline Product Catalogue Enrichment Job")
    parser.add_argument("--model-id", type=str, help="Specific model ID to enrich")
    parser.add_argument("--limit", type=int, default=5, help="Number of models to evaluate")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    job = JobProductEnrichment()
    proposals = job.run(limit=args.limit, specific_model_id=args.model_id)
    print(f"Generated {len(proposals)} proposals.")


if __name__ == "__main__":
    main()
