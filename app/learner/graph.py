from langgraph.graph import END, START, StateGraph

from app.learner.nodes import combine_results, grade_reading, grade_writing, load_assessment, persist_submission
from app.learner.state import LearnerState


def build_learner_graph():
    graph = StateGraph(LearnerState)
    graph.add_node("load_assessment", load_assessment)
    graph.add_node("grade_reading", grade_reading)
    graph.add_node("grade_writing", grade_writing)
    graph.add_node("combine_results", combine_results)
    graph.add_node("persist_submission", persist_submission)
    graph.add_edge(START, "load_assessment")
    graph.add_edge("load_assessment", "grade_reading")
    graph.add_edge("grade_reading", "grade_writing")
    graph.add_edge("grade_writing", "combine_results")
    graph.add_edge("combine_results", "persist_submission")
    graph.add_edge("persist_submission", END)
    return graph.compile()
