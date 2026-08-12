# Search Observer Model Arena bounded concurrency — #552

## Incident

Model Arena replay run #4 (`31549214165`) reached the 20-minute workflow timeout while executing 16 LLM-only calls sequentially. Exact-SHA gate and immutable replay-corpus download passed. Search was not repeated.

## Corrective contract

- maximum Arena concurrency: 4;
- external wall-clock timeout per configured model/case call: 45 seconds on Stage;
- timeout becomes a normal observation with `error_code=arena_call_timeout` instead of aborting the Arena;
- workflow wall-clock cap reduced to 10 minutes;
- search calls remain zero;
- `routing_changed=false` remains mandatory;
- call cap remains 24.

This changes benchmark execution only. It does not enable active steering and does not modify SearchGateway/provider policy.
