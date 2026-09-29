import json
import os
import sys
import tempfile
import unittest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from studio.store import Store, ROOT


class McpIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_stdio_handoff_registers_a_review_without_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            project = store.create_project({"title": "MCP integration"})["id"]
            env = {**os.environ, "DIRECTOR_DATA": directory, "PYTHONPATH": str(ROOT)}
            server = StdioServerParameters(command=sys.executable, args=["-m", "studio.mcp_server"], env=env)
            async with stdio_client(server) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    self.assertEqual(len(tools.tools), 18)
                    self.assertFalse(any("approve" in tool.name for tool in tools.tools))

                    async def call(name, arguments):
                        result = await session.call_tool(name, arguments)
                        self.assertFalse(result.isError, result.content)
                        return json.loads(result.content[0].text)

                    action = await call("get_next_action", {"project_id": project})
                    self.assertEqual(action["stage"], "premise")
                    claim = await call("claim_task", {"project_id": project, "agent_name": "Test writer"})
                    result = await call("register_artifact", {"project_id": project, "payload": {"title": "Test premise", "kind": "premise", "stage": "premise", "content": "A courier chooses to return a lost letter and changes her route home.", "prompt": "Write a concise original premise.", "inputs": [], "task_id": claim["task_id"], "task_token": claim["token"]}})
                    await call("submit_for_review", {"version_id": result["version_id"], "task_id": claim["task_id"], "token": claim["token"]})
                    await call("finish_task", {"task_id": claim["task_id"], "token": claim["token"]})
                    action = await call("get_next_action", {"project_id": project})
                    self.assertEqual(action["state"], "awaiting_review")
                    self.assertEqual(store.get_version(result["version_id"])["version"]["status"], "in_review")


if __name__ == "__main__":
    unittest.main()
