from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.teacher.nodes import (
    assessment_review, bump_assessment, bump_passage, generate_passage,
    generate_reading, generate_writing, ingest_node, passage_review,
    publish, validate_assessment, validate_passage,
)
from app.teacher.state import TeacherState


def build_teacher_graph(checkpointer=None):
    graph = StateGraph(TeacherState)
    for name, node in {
        "ingest": ingest_node, "generate_passage": generate_passage,
        "validate_passage": validate_passage,
        "passage_review": passage_review, "bump_passage": bump_passage,
        "generate_reading": generate_reading, "generate_writing": generate_writing,
        "validate": validate_assessment, "assessment_review": assessment_review,
        "bump_assessment": bump_assessment, "publish": publish,
    }.items():
        graph.add_node(name, node)
    graph.add_edge(START, "ingest")
    graph.add_edge("ingest", "generate_passage")
    graph.add_edge("generate_passage", "validate_passage")
    graph.add_edge("validate_passage", "passage_review")
    graph.add_conditional_edges("passage_review", lambda s: s.get("passage_decision"), {
        "approve": "generate_reading", "reject": "bump_passage",
    })
    graph.add_edge("bump_passage", "generate_passage")
    graph.add_edge("generate_reading", "generate_writing")
    graph.add_edge("generate_writing", "validate")
    graph.add_edge("validate", "assessment_review")
    graph.add_conditional_edges("assessment_review", lambda s: s.get("assessment_decision"), {
        "approve": "publish", "reject": "bump_assessment",
    })
    graph.add_edge("bump_assessment", "generate_reading")
    graph.add_edge("publish", END)
    return graph.compile(checkpointer=checkpointer or MemorySaver())
