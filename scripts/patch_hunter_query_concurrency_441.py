from pathlib import Path

path = Path("app/discovery.py")
text = path.read_text(encoding="utf-8")
old = '''    raw_results: list[dict] = []
    search_diagnostics: list[SearchDiagnostics] = []
    gateway = get_search_gateway()
    policy = search_policy_from_env()
    for query in queries:
        response = await gateway.search(
            SearchRequest(
                query=query,
                limit=req.results_per_query,
                mission_id=mission_id,
                correlation_id=correlation_id,
            ),
            policy,
        )
        search_diagnostics.append(response.diagnostics)
        raw_results.extend(item.as_legacy_dict() for item in response.results)
'''
new = '''    raw_results: list[dict] = []
    search_diagnostics: list[SearchDiagnostics] = []
    gateway = get_search_gateway()
    policy = search_policy_from_env()

    async def search_query(query: str):
        return await gateway.search(
            SearchRequest(
                query=query,
                limit=req.results_per_query,
                mission_id=mission_id,
                correlation_id=correlation_id,
            ),
            policy,
        )

    responses = await asyncio.gather(*(search_query(query) for query in queries))
    for response in responses:
        search_diagnostics.append(response.diagnostics)
        raw_results.extend(item.as_legacy_dict() for item in response.results)
'''
if old not in text:
    if new in text:
        print("hunter query concurrency patch already applied")
        raise SystemExit(0)
    raise SystemExit("expected sequential Hunter search block not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
print("applied bounded-by-provider Hunter query concurrency patch")
