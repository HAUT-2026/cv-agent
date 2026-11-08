"""LangGraph CLI entrypoint for the CVAgent workflow."""

from cvagent.workflow.graph import build_graph


# The API server owns checkpoint persistence in `langgraph dev`.
# The Role 2–4 adapters remain synthetic until those roles are connected.
graph = build_graph(checkpointer=False)
