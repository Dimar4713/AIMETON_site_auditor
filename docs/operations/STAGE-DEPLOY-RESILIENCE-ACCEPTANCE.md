# Stage deploy resilience acceptance

Acceptance criteria affected:

- stage deploy performs no PyPI access;
- exact SHA verification remains mandatory;
- preflight uses only local runner capabilities and live stage health;
- Tavily and Yandex stage policies expose explicit quotas and mission budgets;
- deployment evidence records dependency installation disabled and provider order;
- controlled self-audit must prove `selected → called → returned → accepted/rejected → used_in_report`.

Related: #336.
