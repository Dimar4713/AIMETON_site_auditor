from __future__ import annotations

import asyncio
import json
from uuid import uuid4

import httpx

from app.search_gateway import SearchRequest, get_search_gateway
from app.search_gateway.providers import ProviderError


def redact(value: str, secrets: list[str]) -> str:
    output = value
    for secret in secrets:
        if secret:
            output = output.replace(secret, "[redacted]")
    return output[:700]


def credential_shape(gateway) -> dict:
    yandex = getattr(gateway._providers["yandex"], "_provider", gateway._providers["yandex"])
    tavily = getattr(gateway._providers["tavily"], "_provider", gateway._providers["tavily"])
    folder = yandex._folder_id
    return {
        "yandex_folder_length": len(folder),
        "yandex_folder_ascii": folder.isascii(),
        "yandex_folder_ascii_alnum": folder.isascii() and folder.isalnum(),
        "yandex_folder_first_codepoint": ord(folder[0]) if folder else None,
        "tavily_key_length": len(tavily._api_key),
        "tavily_key_expected_prefix": tavily._api_key.startswith("tvly-"),
    }


async def tavily_usage_diagnostic(scheduled_provider) -> dict:
    provider = getattr(scheduled_provider, "_provider", scheduled_provider)
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=False) as client:
        response = await client.get(
            "https://api.tavily.com/usage",
            headers={
                "Authorization": f"Bearer {provider._api_key}",
                "User-Agent": "AIMETON-Search-Benchmark/1.0",
                "Accept": "application/json",
            },
        )
    safe_headers = {
        key.lower(): value
        for key, value in response.headers.items()
        if key.lower() in {"content-type", "server", "x-request-id", "cf-ray"}
    }
    detail = ""
    try:
        payload = response.json()
        if isinstance(payload, dict):
            # Do not expose account IDs or plan balances; only whether expected sections exist.
            detail = json.dumps(
                {
                    "has_key_section": isinstance(payload.get("key"), dict),
                    "has_account_section": isinstance(payload.get("account"), dict),
                    "error": payload.get("error") or payload.get("message"),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        else:
            detail = str(payload)
    except Exception:
        detail = response.text
    return {
        "status_code": response.status_code,
        "headers": safe_headers,
        "detail": redact(detail, [provider._api_key]),
    }


async def raw_error_detail(provider_name: str, scheduled_provider, request: SearchRequest) -> dict:
    provider = getattr(scheduled_provider, "_provider", scheduled_provider)
    if provider_name == "tavily":
        url = "https://api.tavily.com/search"
        headers = {
            "Authorization": f"Bearer {provider._api_key}",
            "User-Agent": "AIMETON-Search-Benchmark/1.0",
            "Accept": "application/json",
        }
        body = {
            "query": request.query,
            "search_depth": "basic",
            "max_results": 10,
            "include_answer": False,
            "include_raw_content": False,
        }
        secrets = [provider._api_key]
    elif provider_name == "yandex":
        url = "https://searchapi.api.cloud.yandex.net/v2/web/search"
        headers = {"Authorization": f"Api-Key {provider._api_key}"}
        body = {
            "query": {
                "searchType": "SEARCH_TYPE_RU",
                "queryText": request.query,
                "familyMode": "FAMILY_MODE_MODERATE",
                "page": "0",
                "fixTypoMode": "FIX_TYPO_MODE_ON",
            },
            "groupSpec": {
                "groupMode": "GROUP_MODE_FLAT",
                "groupsOnPage": "10",
                "docsInGroup": "1",
            },
            "maxPassages": "3",
            "l10N": "LOCALIZATION_RU",
            "folderId": provider._folder_id,
            "responseFormat": "FORMAT_XML",
        }
        secrets = [provider._api_key, provider._folder_id]
    else:
        return {}

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=False) as client:
        response = await client.post(url, headers=headers, json=body)
    safe_headers = {
        key.lower(): value
        for key, value in response.headers.items()
        if key.lower() in {"content-type", "server", "x-request-id", "x-envoy-upstream-service-time", "cf-ray"}
    }
    try:
        payload = response.json()
        if isinstance(payload, dict):
            safe_payload = {
                key: payload.get(key)
                for key in ("code", "message", "description", "error", "status")
                if payload.get(key) is not None
            }
            detail = json.dumps(safe_payload, ensure_ascii=False, sort_keys=True)
        else:
            detail = str(payload)
    except Exception:
        detail = response.text
    return {
        "status_code": response.status_code,
        "headers": safe_headers,
        "detail": redact(detail, secrets),
    }


async def main() -> None:
    gateway = get_search_gateway()
    print("CREDENTIAL_SHAPE " + json.dumps(credential_shape(gateway), sort_keys=True), flush=True)
    print(
        "TAVILY_USAGE "
        + json.dumps(await tavily_usage_diagnostic(gateway._providers["tavily"]), ensure_ascii=False, sort_keys=True),
        flush=True,
    )

    query = "Стоматология Красноярск официальный сайт компания"
    failed: list[str] = []

    for provider_name in ("yandex", "tavily", "searxng"):
        provider = gateway._providers[provider_name]
        mission = f"bench-provider-probe-{provider_name}-{uuid4()}"
        request = SearchRequest(
            query=query,
            limit=10,
            mission_id=mission,
            correlation_id=mission,
        )
        try:
            results = await provider.search(request, timeout_seconds=20.0)
        except ProviderError as exc:
            diagnostic = await raw_error_detail(provider_name, provider, request)
            print(
                "PROVIDER_DIRECT_FAILURE "
                + json.dumps(
                    {
                        "provider": provider_name,
                        "exception": type(exc).__name__,
                        "reason": str(exc),
                        "http": diagnostic,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                flush=True,
            )
            failed.append(provider_name)
            continue
        except Exception as exc:
            print(
                "PROVIDER_DIRECT_FAILURE "
                + json.dumps(
                    {
                        "provider": provider_name,
                        "exception": type(exc).__name__,
                        "reason": str(exc)[:300],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                flush=True,
            )
            failed.append(provider_name)
            continue

        hosts = []
        for item in results[:5]:
            url = str(item.url)
            host = url.split("/", 3)[2] if "://" in url else url
            hosts.append(host)
        print(
            "PROVIDER_DIRECT_SUCCESS "
            + json.dumps(
                {
                    "provider": provider_name,
                    "result_count": len(results),
                    "top_hosts": hosts,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            flush=True,
        )
        if not results:
            failed.append(provider_name)

    if failed:
        raise SystemExit("provider_preflight_failed:" + ",".join(failed))


if __name__ == "__main__":
    asyncio.run(main())
