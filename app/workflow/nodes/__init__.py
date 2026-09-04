"""Generation nodes shared by the FastAPI teacher graph."""

from app.workflow.nodes.ingest_node import ingest_node
from app.workflow.nodes.passage_node import passage_node
from app.workflow.nodes.reading_node import reading_node

__all__ = ["ingest_node", "passage_node", "reading_node"]
