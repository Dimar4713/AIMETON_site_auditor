"""Compatibility import for the canonical company-intelligence runtime.

The previous implementation contained its own SearXNG client. Keeping this
module as a thin import prevents MCP and HTTP paths from diverging again.
"""

from app.company_intelligence_runtime import run_company_intelligence

__all__ = ["run_company_intelligence"]
