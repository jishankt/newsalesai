"""
Execute Node for Kepler Tech SalesAI.
Executes deterministic catalog tools or prepares specialist agent prompts based on the route.
"""

from typing import Dict, Any, List
from workflow.nodes.base_node import BaseNode
from workflow.context import WorkflowContext
from agent.tool_executor import catalog_tool_executor


class ExecuteNode(BaseNode):
    name: str = "EXECUTE_NODE"

    def execute(self, ctx: WorkflowContext) -> WorkflowContext:
        step = ctx.trace.start_step(self.name)
        tool_name = ctx.decision.tool if ctx.decision else None
        tool_args = ctx.decision.tool_arguments if ctx.decision else {}
        route_str = ctx.target_route or "qualification"

        # 1. Map Specialist Persona
        if route_str in ("social", "business_info"):
            ctx.active_agent = "Front Desk Concierge"
        elif route_str in ("comparison", "support"):
            ctx.active_agent = "Technical & Comparison Specialist"
        elif route_str in ("guardrail", "lead"):
            ctx.active_agent = "Sales & Quotation Specialist"
        else:
            ctx.active_agent = "Product & Catalog Specialist"

        # 2. Execute Deterministic Tool if requested
        if tool_name:
            try:
                res = catalog_tool_executor.execute_tool(tool_name, tool_args)
                ctx.tool_outputs.append(res)

                # Extract product cards (send only once per product per conversation)
                raw_cards = []
                if res.get("cards"):
                    raw_cards.extend(res["cards"])
                elif res.get("product_cards"):
                    raw_cards.extend(res["product_cards"])
                elif res.get("product"):
                    raw_cards.append(catalog_tool_executor.format_card(res["product"], "hardware"))

                msg_l = (ctx.normalized_message or ctx.raw_message or "").lower()
                is_explicit_cards = any(w in msg_l for w in [
                    "show card", "show cards", "show product card", "show printer card", "show again",
                    "show options", "show recommendations", "show all options", "show products", "show printers"
                ])
                disp_list = list(ctx.state.displayed_product_ids) if ctx.state else []
                if not is_explicit_cards and disp_list:
                    def _card_matches_displayed(c_dict):
                        import re
                        def _norm(s):
                            return re.sub(r"[^a-z0-9]", "", str(s).lower())
                        keys = set()
                        for f in ("id", "sku", "model", "canonical_id"):
                            v = c_dict.get(f)
                            if v:
                                keys.add(str(v).strip().lower())
                                keys.add(_norm(v))
                        specs_t = c_dict.get("specifications_table") or {}
                        for sk in ("SKU", "sku", "Model", "model"):
                            v = specs_t.get(sk)
                            if v:
                                keys.add(str(v).strip().lower())
                                keys.add(_norm(v))
                        n_str = (c_dict.get("name") or "") + " " + (c_dict.get("display_name") or "") + " " + (c_dict.get("model") or "")
                        n_models = re.findall(r"\b(?:sc-?)?(?:[tpf]\d{3,5}[a-z0-9]*|ds-?\d{3,5}[a-z0-9]*|cx-?[0-9o]{1,2}[a-z0-9]*|cy-?[0-9o]{1,2}[a-z0-9]*|cz-?[0-9o]{1,2}[a-z0-9]*|am-?c\d{3,4}[a-z0-9]*|wf-?(?:c|m)?\d{3,5}[a-z0-9]*)\b", n_str.lower())
                        for nm in n_models:
                            keys.add(nm)
                            keys.add(_norm(nm))
                        for d in disp_list:
                            ds = str(d).strip().lower()
                            if ds in keys or _norm(ds) in keys:
                                return True
                            for k in keys:
                                if k and (k in ds or ds in k):
                                    return True
                        return False

                    fresh_cards = [c for c in raw_cards if not _card_matches_displayed(c)]
                    ctx.product_cards.extend(fresh_cards)
                else:
                    ctx.product_cards.extend(raw_cards)

                # Extract consumable cards
                if res.get("consumable_cards"):
                    ctx.consumable_cards.extend(res["consumable_cards"])

                # If tool returned a direct summary/reply, store it
                if res.get("consumables_summary"):
                    ctx.response_text = res["consumables_summary"]
                    ctx.source = "tool:get_compatible_consumables"
                elif res.get("reply"):
                    ctx.response_text = res["reply"]
                    ctx.source = f"tool:{tool_name}"

                # Extract suggested chips
                if res.get("suggested_chips"):
                    ctx.suggested_chips.extend(res["suggested_chips"])

                step.complete(
                    summary=f"Executed tool '{tool_name}' ({len(ctx.product_cards)} product cards, {len(ctx.consumable_cards)} consumable cards)",
                    details={"tool": tool_name, "args": tool_args, "result_count": res.get("count", len(ctx.product_cards))}
                )
            except Exception as e:
                step.fail(f"Tool execution failed: {e}")
        else:
            step.complete(summary=f"Specialist '{ctx.active_agent}' activated (no tool execution required)")

        return ctx
