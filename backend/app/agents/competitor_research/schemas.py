"""Internal data shapes for Competitor Research.

The scrape + profile-extraction shape is `CompanyProfile` from
`company_analyzer.schemas` — reused directly rather than duplicated,
since a competitor's own profile is extracted the exact same way a
company's is."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class GeneratedComparison:
    """Claude's structured output for `generate_comparison`."""

    product_pricing_comparison: str | None = None
    marketing_strategy_analysis: str | None = None
    competitive_gaps: str | None = None
    strategic_recommendations: str | None = None
