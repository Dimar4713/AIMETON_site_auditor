from __future__ import annotations

import json
import os

import httpx


endpoint = "https://searchapi.api.cloud.yandex.net/v2/web/search"
key = os.environ["YANDEX_SEARCH_API_KEY"]
folder = os.environ["YANDEX_CLOUD_FOLDER_ID"]
query = "Стоматология Красноярск официальный сайт компания"

good = {
    "query": {
        "searchType": "SEARCH_TYPE_RU",
        "queryText": query,
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
    "folderId": folder,
    "responseFormat": "FORMAT_XML",
}

variants: dict[str, dict] = {
    "01_good_baseline": good,
    "02_good_plus_region_225": {**good, "region": "225"},
    "03_good_reduced_group_spec": {
        **good,
        "groupSpec": {"groupsOnPage": "10"},
    },
}
no_passages = dict(good)
no_passages.pop("maxPassages")
variants["04_good_without_max_passages"] = no_passages
variants["05_runtime_exact"] = {
    "query": dict(good["query"]),
    "groupSpec": {"groupsOnPage": "10"},
    "region": "225",
    "l10N": "LOCALIZATION_RU",
    "folderId": folder,
    "responseFormat": "FORMAT_XML",
}

with httpx.Client(timeout=20.0) as client:
    for name, payload in variants.items():
        response = client.post(
            endpoint,
            headers={
                "Authorization": f"Api-Key {key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        message = ""
        try:
            body = response.json()
            if isinstance(body, dict):
                message = str(body.get("message") or body.get("error") or "")[:120]
        except Exception:
            pass
        print(
            json.dumps(
                {"variant": name, "status": response.status_code, "message": message},
                ensure_ascii=False,
            ),
            flush=True,
        )
