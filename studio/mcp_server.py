"""stdio MCP interface, sharing the dashboard's storage and workflow rules."""
from mcp.server.fastmcp import FastMCP
from .agent_tools import TOOLS

mcp = FastMCP("Director Studio", instructions="Local, approval-gated film production. Read the next action, claim one task, pin approved versions, register work and submit it for director review. Tools cannot approve or spend credits.")
for name, function in TOOLS.items():
    mcp.add_tool(function, name=name)

if __name__ == "__main__":
    mcp.run(transport="stdio")
