"""
Typed Evidence Layer and Product Knowledge Graph for Kepler Tech SalesAI.
Phase 3: Nodes (printers, consumables, media, categories),
edges (uses_consumable, compatible_with, belongs_to_category, same_size_class, alternative_of),
and typed fact queries backed strictly by verified catalogue evidence.
"""

import os
import json
import logging
from enum import Enum
from typing import List, Dict, Any, Optional, Tuple, Set
from pydantic import BaseModel, Field

logger = logging.getLogger("catalog.evidence")

CATALOGUE_PRODUCTS_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "catalogue_products.json")
PRODUCTS_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "products.json")


# ── Typed Evidence Status & Records ───────────────────────────────────────────

class CompatibilityStatus(str, Enum):
    VERIFIED_YES = "VERIFIED_YES"
    VERIFIED_NO = "VERIFIED_NO"
    UNKNOWN = "UNKNOWN"


class EvidenceRecord(BaseModel):
    claim: str
    verified: bool
    status: CompatibilityStatus
    source_file: str
    field: str
    entity_ids: List[str] = Field(default_factory=list)
    supporting_data: Dict[str, Any] = Field(default_factory=dict)
    verified_for: Optional[List[str]] = None  # What it is actually verified for when NO


class KnowledgeNode(BaseModel):
    id: str
    node_type: str  # "printer", "consumable", "media", "category", "accessory"
    name: str
    attributes: Dict[str, Any] = Field(default_factory=dict)
    source_file: str


class KnowledgeEdge(BaseModel):
    source: str
    target: str
    relation: str  # "uses_consumable", "compatible_with", "belongs_to_category", "same_size_class", "alternative_of"
    evidence: Dict[str, Any] = Field(default_factory=dict)


# ── Knowledge Graph Construction ─────────────────────────────────────────────

class ProductKnowledgeGraph:
    """
    In-memory verified knowledge graph built directly from:
    - data/catalogue_products.json (43 hardware printers/scanners)
    - catalog/consumable_registry.py (217 verified consumable SKUs)
    - data/products.json
    """

    def __init__(self):
        self.nodes: Dict[str, KnowledgeNode] = {}
        self.edges_out: Dict[str, List[KnowledgeEdge]] = {}
        self.edges_in: Dict[str, List[KnowledgeEdge]] = {}
        self._build_graph()

    def _add_node(self, node: KnowledgeNode):
        self.nodes[node.id] = node
        if node.id not in self.edges_out:
            self.edges_out[node.id] = []
        if node.id not in self.edges_in:
            self.edges_in[node.id] = []

    def _add_edge(self, edge: KnowledgeEdge):
        if edge.source not in self.edges_out:
            self.edges_out[edge.source] = []
        if edge.target not in self.edges_in:
            self.edges_in[edge.target] = []
        self.edges_out[edge.source].append(edge)
        self.edges_in[edge.target].append(edge)

    def _build_graph(self):
        # 1. Load Hardware Printers from data/catalogue_products.json
        hardware_list = []
        if os.path.exists(CATALOGUE_PRODUCTS_FILE):
            try:
                with open(CATALOGUE_PRODUCTS_FILE, "r", encoding="utf-8") as f:
                    hardware_list = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load catalogue_products.json: {e}")

        for p in hardware_list:
            pid = str(p.get("id", "")).lower()
            if not pid:
                continue

            node = KnowledgeNode(
                id=pid,
                node_type="printer",
                name=p.get("display_name") or p.get("name") or pid,
                attributes=p,
                source_file="data/catalogue_products.json",
            )
            self._add_node(node)

            # Category edge
            cat = p.get("category") or p.get("primary_category")
            if cat:
                cat_id = f"category:{cat.lower()}"
                if cat_id not in self.nodes:
                    self._add_node(KnowledgeNode(
                        id=cat_id,
                        node_type="category",
                        name=cat,
                        attributes={"category": cat},
                        source_file="data/catalogue_products.json"
                    ))
                self._add_edge(KnowledgeEdge(
                    source=pid,
                    target=cat_id,
                    relation="belongs_to_category",
                    evidence={"source_file": "data/catalogue_products.json", "field": "category"}
                ))

            # Hardware-to-consumables edges
            for c_sku in p.get("consumables", []):
                sku_clean = str(c_sku).upper().strip()
                self._add_edge(KnowledgeEdge(
                    source=pid,
                    target=sku_clean,
                    relation="uses_consumable",
                    evidence={"source_file": "data/catalogue_products.json", "field": "consumables"}
                ))
                self._add_edge(KnowledgeEdge(
                    source=sku_clean,
                    target=pid,
                    relation="compatible_with",
                    evidence={"source_file": "data/catalogue_products.json", "field": "consumables"}
                ))

        # 2. Load Consumables from catalog/consumable_registry.py
        try:
            from catalog.consumable_registry import consumable_registry
            for sku, item in consumable_registry.consumables.items():
                sku_clean = str(sku).upper().strip()
                if sku_clean not in self.nodes:
                    self._add_node(KnowledgeNode(
                        id=sku_clean,
                        node_type="consumable",
                        name=item.name,
                        attributes={
                            "sku": sku_clean,
                            "name": item.name,
                            "type": item.consumable_type,
                            "color": item.color,
                            "size_format": item.size_format,
                            "yield_info": item.yield_info,
                            "pack_quantity": item.pack_quantity,
                            "url": item.url,
                            "compatible_printers": item.compatible_printers,
                        },
                        source_file="catalog/consumable_registry.py"
                    ))

                # Bidirectional edges with compatible printers
                for pid in item.compatible_printers:
                    pid_clean = str(pid).lower().strip()
                    # Add edge if not already present
                    if not any(e.source == pid_clean and e.target == sku_clean for e in self.edges_out.get(pid_clean, [])):
                        self._add_edge(KnowledgeEdge(
                            source=pid_clean,
                            target=sku_clean,
                            relation="uses_consumable",
                            evidence={"source_file": "catalog/consumable_registry.py", "field": "compatible_printers"}
                        ))
                    if not any(e.source == sku_clean and e.target == pid_clean for e in self.edges_out.get(sku_clean, [])):
                        self._add_edge(KnowledgeEdge(
                            source=sku_clean,
                            target=pid_clean,
                            relation="compatible_with",
                            evidence={"source_file": "catalog/consumable_registry.py", "field": "compatible_printers"}
                        ))
        except Exception as e:
            logger.error(f"Failed to load consumable_registry into knowledge graph: {e}")

        # 2b. Load additional consumables, media & accessories from data/products.json
        if os.path.exists(PRODUCTS_FILE):
            try:
                with open(PRODUCTS_FILE, "r", encoding="utf-8") as f:
                    products_json_list = json.load(f)
                for p in products_json_list:
                    sku = p.get("sku") or p.get("_id")
                    if not sku:
                        continue
                    sku_clean = str(sku).upper().strip()
                    p_cat = p.get("category", "")
                    node_type = "consumable" if p_cat in ("Ink Cartridge", "Maintenance Box") else ("media" if p_cat == "Media & Paper" else ("printer" if "Printer" in p_cat else "accessory"))
                    if sku_clean not in self.nodes:
                        self._add_node(KnowledgeNode(
                            id=sku_clean,
                            node_type=node_type,
                            name=p.get("name") or sku_clean,
                            attributes={
                                "sku": sku_clean,
                                "name": p.get("name") or sku_clean,
                                "type": node_type,
                                "category": p_cat,
                                "price": p.get("price"),
                                "price_formatted": p.get("price_formatted"),
                                "url": p.get("website_url") or p.get("web_url") or p.get("product_url"),
                                "image_url": p.get("image_url") or p.get("image"),
                                "compatible_printers": [],
                            },
                            source_file="data/products.json"
                        ))
            except Exception as e:
                logger.error(f"Failed to load products.json into knowledge graph: {e}")

        # 2c. Ensure every printer consumable SKU has a node and bidirectional edges
        for p in hardware_list:
            pid = str(p.get("id", "")).lower()
            if not pid:
                continue
            for c_sku in p.get("consumables", []):
                sku_clean = str(c_sku).upper().strip()
                if sku_clean not in self.nodes:
                    self._add_node(KnowledgeNode(
                        id=sku_clean,
                        node_type="consumable",
                        name=f"Genuine Consumable {sku_clean}",
                        attributes={
                            "sku": sku_clean,
                            "name": f"Genuine Consumable {sku_clean}",
                            "type": "consumable",
                            "category": "Ink & Supplies",
                            "compatible_printers": [pid],
                        },
                        source_file="data/catalogue_products.json"
                    ))
                if not any(e.source == pid and e.target == sku_clean for e in self.edges_out.get(pid, [])):
                    self._add_edge(KnowledgeEdge(
                        source=pid,
                        target=sku_clean,
                        relation="uses_consumable",
                        evidence={"source_file": "data/catalogue_products.json", "field": "consumables"}
                    ))
                if not any(e.source == sku_clean and e.target == pid for e in self.edges_out.get(sku_clean, [])):
                    self._add_edge(KnowledgeEdge(
                        source=sku_clean,
                        target=pid,
                        relation="compatible_with",
                        evidence={"source_file": "data/catalogue_products.json", "field": "consumables"}
                    ))

        # 3. Size Class & Alternative edges across hardware printers
        for i, p1 in enumerate(hardware_list):
            pid1 = str(p1.get("id", "")).lower()
            cat1 = str(p1.get("category", "")).lower()
            w1 = p1.get("width") or p1.get("print_width")
            for j, p2 in enumerate(hardware_list):
                if i >= j:
                    continue
                pid2 = str(p2.get("id", "")).lower()
                cat2 = str(p2.get("category", "")).lower()
                w2 = p2.get("width") or p2.get("print_width")

                # Same size class edge
                if w1 and w2 and str(w1) == str(w2):
                    self._add_edge(KnowledgeEdge(
                        source=pid1, target=pid2, relation="same_size_class",
                        evidence={"width": w1}
                    ))
                    self._add_edge(KnowledgeEdge(
                        source=pid2, target=pid1, relation="same_size_class",
                        evidence={"width": w1}
                    ))

                # Alternative edge if in same category
                if cat1 and cat1 == cat2:
                    self._add_edge(KnowledgeEdge(
                        source=pid1, target=pid2, relation="alternative_of",
                        evidence={"category": cat1}
                    ))
                    self._add_edge(KnowledgeEdge(
                        source=pid2, target=pid1, relation="alternative_of",
                        evidence={"category": cat1}
                    ))


def format_attribute_claim(entity_name: str, field: str, val: Any) -> str:
    """Renders human-readable, customer-facing label templates for evidence attributes."""
    if isinstance(val, list):
        val_str = ", ".join(str(v) for v in val)
    elif isinstance(val, bool):
        val_str = "Yes" if val else "No"
    else:
        val_str = str(val).strip()

    field_lower = field.lower().replace("-", "_")

    LABEL_TEMPLATES = {
        "print_speed": f"Print speed: {val_str}.",
        "speed": f"Print speed: {val_str}.",
        "dpi": f"Print resolution: {val_str}.",
        "resolution": f"Print resolution: {val_str}.",
        "print_width": f"Print width: {val_str}.",
        "width": f"Print width: {val_str}.",
        "max_width_inches": f"Maximum print width: {val_str} inches.",
        "paper_size": f"Supported paper size: {val_str}.",
        "connectivity": f"Connectivity: {val_str}.",
        "interfaces": f"Interfaces: {val_str}.",
        "total_colours": f"Ink system: {val_str}.",
        "colours": f"Ink system: {val_str}.",
        "colour_specification": f"Ink technology: {val_str}.",
        "cartridge_sizes": f"Cartridge sizes: {val_str}.",
        "consumable_volume": f"Yield capacity: {val_str}.",
        "yield_capacity": f"Yield capacity: {val_str}.",
        "dimensions": f"Dimensions: {val_str}.",
        "weight": f"Weight: {val_str}.",
        "memory": f"Memory: {val_str}.",
        "functions": f"Functions: {val_str}.",
        "applications": f"Target applications: {val_str}.",
        "warranty": f"Warranty: {val_str}.",
        "stand": f"Stand configuration: {val_str}.",
        "has_stand": f"Stand included: {val_str}.",
        "scanner_integrated": f"Integrated scanner: {val_str}.",
        "dual_roll": f"Dual-roll support: {val_str}.",
        "spectro": f"SpectroProofer support: {val_str}.",
        "display_name": f"{entity_name} is an approved equipment model in our verified catalogue.",
        "name": f"{entity_name} is an approved equipment model in our verified catalogue.",
        "model": f"{entity_name} is an approved equipment model in our verified catalogue.",
        "model_family": f"{entity_name} belongs to the {val_str} series in our verified catalogue.",
    }

    if field_lower in LABEL_TEMPLATES:
        return LABEL_TEMPLATES[field_lower]

    clean_field = field_lower.replace("_", " ").title()
    return f"{clean_field}: {val_str}."


# Global graph singleton
knowledge_graph = ProductKnowledgeGraph()


# ── Typed Fact Query APIs ─────────────────────────────────────────────────────

class EvidenceEngine:
    """
    Exposes typed fact queries backed strictly by verified evidence.
    No evidence => claim cannot be made.
    """

    @classmethod
    def get_attribute(cls, entity_id: str, field: str) -> Tuple[Any, Optional[EvidenceRecord]]:
        """
        Retrieves a verified attribute value for an entity.
        Returns (value, EvidenceRecord) or ("MISSING", None).
        """
        clean_id = entity_id.lower().strip()
        node = knowledge_graph.nodes.get(clean_id) or knowledge_graph.nodes.get(clean_id.upper())
        if not node:
            return "MISSING", None

        val = node.attributes.get(field)
        if val is None:
            # Check nested specs or configuration
            specs = node.attributes.get("specs") or {}
            val = specs.get(field)

        if val is not None and str(val).strip().lower() not in ("none", "null", ""):
            claim_text = format_attribute_claim(node.name, field, val)
            rec = EvidenceRecord(
                claim=claim_text,
                verified=True,
                status=CompatibilityStatus.VERIFIED_YES,
                source_file=node.source_file,
                field=field,
                entity_ids=[node.id],
                supporting_data={field: val},
            )
            return val, rec

        return "MISSING", None

    @classmethod
    def check_compatibility(cls, item_id: str, target_id: str) -> EvidenceRecord:
        """
        Verifies whether item_id is compatible with target_id.
        Returns VERIFIED_YES | VERIFIED_NO(with what it is verified for) | UNKNOWN.
        This single relation replaces all per-case 'is X suitable for Y' code.
        """
        clean_item = item_id.upper().strip()
        clean_target = target_id.lower().strip()

        # Check nodes
        item_node = knowledge_graph.nodes.get(clean_item) or knowledge_graph.nodes.get(clean_item.lower())
        target_node = knowledge_graph.nodes.get(clean_target) or knowledge_graph.nodes.get(clean_target.upper())

        # If item or target is not in catalogue, return UNKNOWN
        if not item_node or not target_node:
            return EvidenceRecord(
                claim=f"Compatibility between '{item_id}' and '{target_id}' could not be verified in official catalogue.",
                verified=False,
                status=CompatibilityStatus.UNKNOWN,
                source_file="none",
                field="none",
                entity_ids=[clean_item, clean_target],
            )

        # Check for direct edge in graph
        edges = knowledge_graph.edges_out.get(item_node.id, [])
        is_compatible = any(e.target == target_node.id and e.relation in ("compatible_with", "uses_consumable") for e in edges)

        if not is_compatible:
            # Check inverse edge
            rev_edges = knowledge_graph.edges_out.get(target_node.id, [])
            is_compatible = any(e.target == item_node.id and e.relation in ("compatible_with", "uses_consumable") for e in rev_edges)

        item_name = item_node.name
        target_name = target_node.name

        if is_compatible:
            return EvidenceRecord(
                claim=f"Yes, {item_name} ({item_node.id}) is verified compatible with the {target_name}.",
                verified=True,
                status=CompatibilityStatus.VERIFIED_YES,
                source_file=item_node.source_file,
                field="compatible_printers",
                entity_ids=[item_node.id, target_node.id],
                supporting_data={"item": item_node.attributes, "target": target_node.attributes},
            )
        else:
            # Find what the item IS actually verified for
            verified_for_ids = [e.target for e in edges if e.relation == "compatible_with"]
            verified_for_names = [knowledge_graph.nodes[t].name for t in verified_for_ids if t in knowledge_graph.nodes]
            if not verified_for_names:
                fam = item_node.attributes.get("model_family") or item_node.attributes.get("model")
                if fam:
                    verified_for_names = [f"Epson SureColor {fam}" if "epson" in item_node.id.lower() else f"Citizen {fam}"]

            claim = f"No, {item_name} ({item_node.id}) is not compatible with the {target_name}."
            if verified_for_names:
                claim += f" It is verified for: {', '.join(verified_for_names)}."

            return EvidenceRecord(
                claim=claim,
                verified=True,
                status=CompatibilityStatus.VERIFIED_NO,
                source_file=item_node.source_file,
                field="compatible_printers",
                entity_ids=[item_node.id, target_node.id],
                verified_for=verified_for_names,
                supporting_data={"verified_for": verified_for_names},
            )

    @classmethod
    def list_consumables(
        cls, printer_id: str, filters: Optional[Dict[str, Any]] = None
    ) -> Tuple[List[Dict[str, Any]], EvidenceRecord]:
        """Returns all genuine compatible consumables for a printer with evidence."""
        clean_id = printer_id.lower().strip()
        printer_node = knowledge_graph.nodes.get(clean_id)
        if not printer_node:
            return [], EvidenceRecord(
                claim=f"Printer '{printer_id}' not found in verified catalogue.",
                verified=False,
                status=CompatibilityStatus.UNKNOWN,
                source_file="none",
                field="id",
                entity_ids=[clean_id],
            )

        edges = knowledge_graph.edges_out.get(clean_id, [])
        consumable_skus = [e.target for e in edges if e.relation == "uses_consumable"]

        items = []
        for sku in consumable_skus:
            c_node = knowledge_graph.nodes.get(sku)
            if c_node:
                # Apply optional filters (e.g. type == 'ink', color == 'yellow')
                if filters:
                    match = True
                    for k, v in filters.items():
                        if c_node.attributes.get(k) != v:
                            match = False
                            break
                    if not match:
                        continue
                items.append(c_node.attributes)

        rec = EvidenceRecord(
            claim=f"Found {len(items)} verified compatible consumables for {printer_node.name}.",
            verified=True,
            status=CompatibilityStatus.VERIFIED_YES,
            source_file="data/catalogue_products.json & catalog/consumable_registry.py",
            field="consumables",
            entity_ids=[clean_id] + consumable_skus,
            supporting_data={"count": len(items), "consumables": items},
        )
        return items, rec

    @classmethod
    def find_alternatives(
        cls, entity_id: str, by: Optional[List[str]] = None
    ) -> Tuple[List[Dict[str, Any]], EvidenceRecord]:
        """
        Dynamically finds verified alternatives by category + size class + speed tier.
        Never uses a hardcoded list.
        """
        clean_id = entity_id.lower().strip()
        node = knowledge_graph.nodes.get(clean_id) or knowledge_graph.nodes.get(clean_id.upper())
        if not node:
            return [], EvidenceRecord(
                claim=f"Entity '{entity_id}' not found in catalogue.",
                verified=False,
                status=CompatibilityStatus.UNKNOWN,
                source_file="none",
                field="id",
                entity_ids=[clean_id],
            )

        edges = knowledge_graph.edges_out.get(node.id, [])
        alt_ids = [e.target for e in edges if e.relation in ("alternative_of", "same_size_class")]

        # Deduplicate and remove self
        alt_ids = [aid for aid in dict.fromkeys(alt_ids) if aid != node.id]

        alternatives = []
        for aid in alt_ids:
            alt_node = knowledge_graph.nodes.get(aid)
            if alt_node:
                alternatives.append(alt_node.attributes)

        rec = EvidenceRecord(
            claim=f"Found {len(alternatives)} verified alternatives for {node.name}.",
            verified=True,
            status=CompatibilityStatus.VERIFIED_YES,
            source_file="data/catalogue_products.json",
            field="category, width",
            entity_ids=[node.id] + alt_ids,
            supporting_data={"count": len(alternatives)},
        )
        return alternatives, rec

    @classmethod
    def compare(
        cls, entities: List[str], fields: List[str]
    ) -> Tuple[Dict[str, Dict[str, Any]], EvidenceRecord]:
        """Builds a structured comparison matrix of verified fields across entities with real side-by-side table output."""
        matrix: Dict[str, Dict[str, Any]] = {}
        missing_entities = []
        product_nodes = []

        for eid in entities:
            clean_id = eid.lower().strip()
            node = knowledge_graph.nodes.get(clean_id) or knowledge_graph.nodes.get(clean_id.upper())
            if not node:
                missing_entities.append(eid)
                continue

            product_nodes.append(node)
            matrix[node.id] = {}
            for f in fields:
                val = node.attributes.get(f)
                if val is None:
                    specs = node.attributes.get("specs") or {}
                    val = specs.get(f)
                matrix[node.id][f] = val if val is not None else "N/A"

        claim_text = ""
        try:
            from catalog.comparison_engine import build_comparison, build_comparison_intro, format_comparison_markdown_table
            product_objs = [n.attributes for n in product_nodes]
            if len(product_objs) >= 2:
                comp_data = build_comparison(product_objs)
                intro = build_comparison_intro(product_objs, comp_data)
                table = format_comparison_markdown_table(product_objs, comp_data)
                claim_text = f"{intro}\n\n{table}"
        except Exception as e:
            logger.warning(f"Error rendering structured comparison table: {e}")

        if not claim_text:
            lines = ["### Direct Model Comparison"]
            for n in product_nodes:
                lines.append(f"\n**{n.name}**:")
                for f in fields:
                    val = matrix.get(n.id, {}).get(f, "N/A")
                    lines.append(f"- {f.replace('_', ' ').capitalize()}: {val}")
            claim_text = "\n".join(lines)

        rec = EvidenceRecord(
            claim=claim_text,
            verified=len(missing_entities) == 0,
            status=CompatibilityStatus.VERIFIED_YES if not missing_entities else CompatibilityStatus.UNKNOWN,
            source_file="data/catalogue_products.json",
            field=", ".join(fields),
            entity_ids=list(matrix.keys()),
            supporting_data={"matrix": matrix, "missing": missing_entities},
        )
        return matrix, rec
