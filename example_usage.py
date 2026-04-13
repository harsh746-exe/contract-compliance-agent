"""Example usage of the MCP workflow entrypoint."""

import asyncio

from compliance_agent.main import run
from compliance_agent.scenarios import load_scenario

scenario = load_scenario("examples/scenarios/compliance_review_case_01")

result = asyncio.run(
    run(
        {
            "task": scenario.goal,
            "documents": [doc.model_dump() for doc in scenario.documents],
            "output_dir": "output/example_usage",
            "run_id": "example_mcp_001",
        }
    )
)

print(result["workflow"])
print(result["run_dir"])
print(sorted(result.get("artifacts", {}).keys()))
