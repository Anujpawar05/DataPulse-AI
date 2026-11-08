import json
import re
from typing import List, Dict, Any, Optional

from ai_agent.backend.providers.manager import ProviderManager
from ai_agent.backend.analytics.insights_store import InsightsStore


def clean_llm_json_response(raw_text: str) -> str:
    """Strip code fences, whitespace, or commentary from LLM output."""
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE).strip()
    # Find matching JSON array or object
    array_match = re.search(r"\[.*\]", text, re.DOTALL)
    if array_match:
        return array_match.group(0).strip()
    return text


def generate_rule_based_narrative(fact: Dict[str, Any]) -> Dict[str, str]:
    """Deterministic fallback narrative engine when LLM providers are unavailable."""
    cat = fact.get("category", "")
    metric = fact.get("metric_name", "")
    obs_fmt = fact.get("observed_value_formatted", "")
    base_fmt = fact.get("baseline_value_formatted", "baseline")
    chg = fact.get("change_percentage")

    if cat == "inventory_risk":
        fact_str = fact.get("observed_fact", "")
        if "transfer viable" in fact_str.lower():
            rec = "Initiate an expedited internal stock transfer from the confirmed surplus hub to balance regional inventory."
        else:
            rec = "Issue an emergency supplier purchase order immediately to prevent stockout and replenish safety stock levels."
        return {
            "headline": fact.get("headline", "Critical Inventory Replenishment Alert"),
            "ai_explanation": (
                f"Physical stock is depleted below the safety threshold. Current run-rate velocity indicates "
                f"depletion within {obs_fmt} if replenishment is not executed promptly."
            ),
            "actionable_recommendation": rec,
        }

    elif cat == "profit_margin":
        return {
            "headline": fact.get("headline", "Profit Margin Divergence Detected"),
            "ai_explanation": (
                f"Operating margin contracted to {obs_fmt} against the historical baseline of {base_fmt}. "
                f"This margin compression indicates elevated promotional discounting or rising unit fulfillment costs."
            ),
            "actionable_recommendation": (
                "Review active promotional coupon rules and discount tiers to restore gross margin health."
            ),
        }

    elif cat == "revenue_trend":
        if chg is not None and chg < 0:
            return {
                "headline": fact.get("headline", "Macro Revenue Deceleration Detected"),
                "ai_explanation": (
                    f"Net revenue dropped to {obs_fmt}, falling {abs(chg):.1f}% below {base_fmt}. "
                    f"Statistical band breach indicates unexpected demand softening or conversion drop."
                ),
                "actionable_recommendation": (
                    "Inspect customer acquisition funnels, checkout completion rates, and category marketing campaigns."
                ),
            }
        else:
            return {
                "headline": fact.get("headline", "Significant Revenue Growth Spike"),
                "ai_explanation": (
                    f"Net revenue surged to {obs_fmt}, exceeding baseline expectations ({base_fmt}) by {chg:+.1f}%. "
                    f"Strong demand momentum observed across key order segments."
                ),
                "actionable_recommendation": (
                    "Capitalize on sales momentum by ensuring inventory depth for trending products and retargeting active buyers."
                ),
            }

    elif cat == "category_shift":
        return {
            "headline": fact.get("headline", "Category Performance Shift"),
            "ai_explanation": (
                f"Category sales distribution shows strong concentration, accounting for {obs_fmt} of platform revenue. "
                f"Maintains a high margin profile supporting baseline profitability."
            ),
            "actionable_recommendation": (
                "Expand catalog breadth and vendor partnerships within this high-performing product category."
            ),
        }

    elif cat == "product_anomaly":
        return {
            "headline": fact.get("headline", "Top Performing SKU Highlight"),
            "ai_explanation": (
                f"Product generated {obs_fmt} in net revenue, leading the product catalog in velocity and profitability."
            ),
            "actionable_recommendation": (
                "Ensure continuous vendor procurement pipeline to avoid supply bottlenecks for this revenue-critical SKU."
            ),
        }

    elif cat == "order_payment_anomaly":
        return {
            "headline": fact.get("headline", "Payment Processing Anomaly"),
            "ai_explanation": (
                f"Payment method experienced an elevated transaction failure rate of {obs_fmt}, above the platform baseline of {base_fmt}. "
                f"Indicates gateway degradation or checkout authorization issues."
            ),
            "actionable_recommendation": (
                "Engage payment gateway technical support to audit network timeout errors and re-route failovers."
            ),
        }

    # Default fallback
    return {
        "headline": fact.get("headline", "Operational Metric Anomaly"),
        "ai_explanation": (
            f"Observed value of {obs_fmt} diverges significantly from the expected baseline ({base_fmt})."
        ),
        "actionable_recommendation": (
            "Review operational logs and warehouse telemetry to verify underlying demand drivers."
        ),
    }


class GroundedInsightsGenerator:
    """Synthesizes executive narratives and actionable recommendations from verified facts.

    Uses ProviderManager (Gemini -> Groq -> Ollama) with deterministic rule fallback.
    Guarantees that numbers, confidence scores, and source evidence are never modified by the LLM.
    """

    def __init__(
        self,
        provider_manager: Optional[ProviderManager] = None,
        store: Optional[InsightsStore] = None,
    ):
        self.provider_manager = provider_manager or ProviderManager()
        self.store = store or InsightsStore()

    def process_and_persist_facts(
        self, facts: List[Dict[str, Any]], force_llm: bool = True
    ) -> List[Dict[str, Any]]:
        """Process fact bundles through the LLM explainer (or fallback) and persist to SQLite."""
        if not facts:
            return []

        # Prepare payload for LLM
        prompt = self._build_synthesis_prompt(facts)
        llm_narratives = {}
        provider_used = "rule_fallback"

        if force_llm:
            try:
                raw_response = self.provider_manager.generate_response(prompt)
                cleaned_json = clean_llm_json_response(raw_response)
                parsed = json.loads(cleaned_json)
                if isinstance(parsed, list):
                    for item in parsed:
                        if isinstance(item, dict) and "fact_index" in item:
                            llm_narratives[item["fact_index"]] = item
                    provider_used = "llm_grounded"
            except Exception as exc:
                # Expected when offline or quota reached; graceful fallback
                provider_used = "rule_fallback"

        persisted_insights = []
        for idx, fact in enumerate(facts):
            narrative = llm_narratives.get(idx)
            if not narrative or not narrative.get("ai_explanation"):
                narrative = generate_rule_based_narrative(fact)
                curr_provider = "rule_fallback"
            else:
                curr_provider = provider_used

            insight_item = {
                "category": fact["category"],
                "severity": fact["severity"],
                "status": "active",
                "headline": str(narrative.get("headline", fact.get("headline", "Business Insight"))),
                "observed_fact": fact["observed_fact"],  # IMMUTABLE
                "ai_explanation": str(narrative.get("ai_explanation", "")).strip(),
                "actionable_recommendation": str(narrative.get("actionable_recommendation", "")).strip(),
                "metric_name": fact["metric_name"],
                "observed_value": fact["observed_value"],
                "observed_value_formatted": fact["observed_value_formatted"],
                "baseline_value": fact.get("baseline_value"),
                "baseline_value_formatted": fact.get("baseline_value_formatted"),
                "change_percentage": fact.get("change_percentage"),
                "statistical_score": fact.get("statistical_score"),
                "detection_method": fact.get("detection_method", "Statistical Analysis"),
                "period_start": fact["period_start"],
                "period_end": fact["period_end"],
                "warehouse_table": fact["warehouse_table"],
                "supporting_sql": fact["supporting_sql"],
                "confidence_score": fact["confidence_score"],  # IMMUTABLE deterministic score
                "ai_provider_used": curr_provider,
                "dimension_key": fact.get("dimension_key", "default"),
            }

            saved = self.store.save_insight(insight_item)
            if saved:
                persisted_insights.append(saved)

        return persisted_insights

    def _build_synthesis_prompt(self, facts: List[Dict[str, Any]]) -> str:
        facts_summary = []
        for idx, f in enumerate(facts):
            facts_summary.append(
                {
                    "fact_index": idx,
                    "category": f["category"],
                    "severity": f["severity"],
                    "metric_name": f["metric_name"],
                    "observed_value": f["observed_value_formatted"],
                    "baseline_value": f.get("baseline_value_formatted"),
                    "observed_fact": f["observed_fact"],
                }
            )

        return f"""You are an executive business analyst for DataPulse AI.
Analyze the following verified warehouse anomaly facts and produce strategic business explanations and actionable recommendations.

STRICT INSTRUCTIONS:
1. Ground your explanation ONLY in the verified facts provided below. Never invent external figures, dates, or root causes.
2. For inventory risks, label projections as estimates. Only recommend stock transfer if the fact states surplus is confirmed; otherwise recommend supplier purchase order.
3. Be concise, executive-level, and operational.
4. Return ONLY a valid JSON array of objects without Markdown formatting or fences.

FACTS TO ANALYZE:
{json.dumps(facts_summary, indent=2)}

REQUIRED JSON OUTPUT FORMAT:
[
  {{
    "fact_index": 0,
    "headline": "Brief executive headline",
    "ai_explanation": "Concise business explanation of why this anomaly matters and likely drivers based on the evidence.",
    "actionable_recommendation": "Specific next action for operational managers."
  }}
]
"""
