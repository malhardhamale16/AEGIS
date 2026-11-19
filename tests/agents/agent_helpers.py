import json


def plan_json(*steps, response=None) -> str:
    """Build the JSON a planner LLM would return. Each step is (skill, args)."""
    return json.dumps(
        {"steps": [{"skill": s, "args": a, "reason": ""} for s, a in steps], "response": response}
    )
