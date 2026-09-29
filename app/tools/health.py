def tool_health(registry) -> dict[str, object]:
    tools = registry.health()
    return {"status": "ok" if all(item["available"] for item in tools) else "degraded", "count": len(tools), "tools": tools}
