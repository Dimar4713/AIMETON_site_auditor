#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

PROTOCOL_VERSION = "2025-06-18"

def post(url: str, message: dict[str, Any], session: str | None = None):
    headers={"Content-Type":"application/json","Accept":"application/json, text/event-stream","MCP-Protocol-Version":PROTOCOL_VERSION}
    if session: headers["Mcp-Session-Id"]=session
    req=Request(url,data=json.dumps(message,separators=(",",":")).encode(),headers=headers,method="POST")
    with urlopen(req,timeout=30) as r:
        session=r.headers.get("Mcp-Session-Id") or session
        text=r.read().decode()
        if "text/event-stream" in r.headers.get("Content-Type",""):
            text=[line[5:].strip() for line in text.splitlines() if line.startswith("data:")][-1]
        return (json.loads(text) if text else None), session

def result(response):
    assert response and "error" not in response and "result" in response, response
    return response["result"]

def payload(tool_result):
    if isinstance(tool_result.get("structuredContent"),dict): return tool_result["structuredContent"]
    for item in tool_result.get("content",[]):
        if isinstance(item,dict) and isinstance(item.get("text"),str):
            parsed=json.loads(item["text"])
            if isinstance(parsed,dict): return parsed
    raise AssertionError(tool_result)

def call(url, session, request_id, name, arguments):
    response,_=post(url,{"jsonrpc":"2.0","id":request_id,"method":"tools/call","params":{"name":name,"arguments":arguments}},session)
    value=result(response); assert value.get("isError") is not True, value
    return payload(value)

def accept(url: str):
    init,session=post(url,{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":PROTOCOL_VERSION,"capabilities":{},"clientInfo":{"name":"aimeton-temporal-acceptance","version":"1"}}})
    result(init); post(url,{"jsonrpc":"2.0","method":"notifications/initialized"},session)
    listed,_=post(url,{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}},session)
    names={tool["name"] for tool in result(listed).get("tools",[])}
    required={"runtime.wait.status","runtime.deadline.check"}; assert required <= names, sorted(names)
    missing="acceptance-missing-intent"
    status=call(url,session,3,"runtime.wait.status",{"wait_id":missing})
    deadline=call(url,session,4,"runtime.deadline.check",{"wait_id":missing})
    assert status.get("status")=="not_found", status
    assert deadline.get("state")=="blocked" and deadline.get("reason")=="blocked:intent_not_found", deadline
    return {"transport":"mcp-streamable-http","session_mode":"stateful" if session else "stateless","endpoint":url,"tools":sorted(required),"status_result":status,"deadline_result":deadline,"read_only":True,"secret_values_exposed":False}

def main():
    p=argparse.ArgumentParser(); p.add_argument("--url",default="https://stage-auditor.aimeton.ru/mcp/"); p.add_argument("--evidence",type=Path); a=p.parse_args()
    evidence=accept(a.url); rendered=json.dumps(evidence,ensure_ascii=False,sort_keys=True,indent=2); print(rendered)
    if a.evidence: a.evidence.parent.mkdir(parents=True,exist_ok=True); a.evidence.write_text(rendered+"\n",encoding="utf-8")
if __name__=="__main__": main()
