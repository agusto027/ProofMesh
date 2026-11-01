import json

from fastapi.testclient import TestClient

from proofmesh.app.main import app


def test_streamable_http_initializes_and_lists_tools():
    headers = {"accept": "application/json, text/event-stream", "content-type": "application/json"}
    with TestClient(app) as client:
        initialized = client.post("/mcp", headers=headers, json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                       "clientInfo": {"name": "smoke-test", "version": "1"}},
        })
        assert initialized.status_code == 200
        session_id = initialized.headers["mcp-session-id"]
        session_headers = {**headers, "mcp-session-id": session_id}
        client.post("/mcp", headers=session_headers, json={
            "jsonrpc": "2.0", "method": "notifications/initialized"})
        response = client.post("/mcp", headers=session_headers, json={
            "jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        assert response.status_code == 200
        payload = json.loads(next(line[6:] for line in response.text.splitlines()
                                  if line.startswith("data: ")))
        names = {tool["name"] for tool in payload["result"]["tools"]}
        assert "proofmesh_run_task" in names
        assert "proofmesh_compare_blind" in names
        run_response = client.post("/mcp", headers=session_headers, json={
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "proofmesh_run_task", "arguments": {
                "prompt": "Summarize this request.",
                "model_profile": {"provider": "mock", "model": "deterministic"},
                "budget_tokens": 2000,
            }},
        })
        run_payload = json.loads(next(line[6:] for line in run_response.text.splitlines()
                                      if line.startswith("data: ")))
        run_data = json.loads(run_payload["result"]["content"][0]["text"])
        assert run_data["status"] == "completed"
        result_response = client.post("/mcp", headers=session_headers, json={
            "jsonrpc": "2.0", "id": 4, "method": "tools/call",
            "params": {"name": "proofmesh_get_result", "arguments": {"run_id": run_data["run_id"]}},
        })
        result_payload = json.loads(next(line[6:] for line in result_response.text.splitlines()
                                         if line.startswith("data: ")))
        result_data = json.loads(result_payload["result"]["content"][0]["text"])
        assert result_data["status"] == "completed"
        assert result_data["answer"]
