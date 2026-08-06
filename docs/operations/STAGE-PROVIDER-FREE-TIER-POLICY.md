# Stage provider free-tier policy

For controlled stage tests, Tavily and Yandex are allowed within explicitly configured free quotas.

Required provider order:

`yandex,tavily,searxng`

Required controls:

- `IDENTITY_SEARCH_ALLOW_PAID_FALLBACK=true` only on stage;
- explicit per-mission budgets;
- explicit global quotas;
- no automatic over-quota continuation;
- no unapproved spend;
- provider success is accepted only when evidence reaches the report.

Related: #336.
