from tools.ontology.build_formal_ontology import (
    CLASS_PARENTS,
    PROPERTIES,
    is_instance_of,
)
from app.services.ontology_rules import ontology_policy


def test_formal_ontology_has_class_hierarchy_and_property_constraints():
    assert CLASS_PARENTS["Passage"] == "LearningResource"
    assert CLASS_PARENTS["Vocabulary"] == "LexicalResource"
    assert is_instance_of("Passage", "EducationalEntity")
    assert is_instance_of("Vocabulary", "LanguageResource")
    assert not is_instance_of("Grammar", "LearningResource")


def test_core_properties_declare_domain_range_and_inverse():
    assert PROPERTIES["TARGETS_GRADE"] == (
        "LearningResource", "Grade", "IS_TARGET_OF"
    )
    assert PROPERTIES["USES_REGISTERED_LEXEME"] == (
        "Passage", "Lexeme", "USED_BY_PASSAGE"
    )
    assert PROPERTIES["REGISTERED_AT_GRADE"] == (
        "LanguageResource", "Grade", "HAS_REGISTERED_RESOURCE"
    )
    assert PROPERTIES["REALIZES_TEXT_TYPE"] == (
        "Passage", "TextType", "REALIZED_BY_PASSAGE"
    )


def test_declarative_policy_contains_core_ontology_constraints():
    rules = {rule["id"]: rule for rule in ontology_policy()["rules"]}
    assert set(rules) == {
        "O-VAL-LENGTH",
        "O-VAL-GRADE-RESOURCE",
        "O-VAL-SOURCE-TERM-USED",
        "O-VAL-REQUIRED-RELATIONS",
    }
    assert rules["O-VAL-REQUIRED-RELATIONS"]["min_count"] == {
        "TARGETS_GRADE": 1,
        "GROUNDED_IN": 1,
        "REALIZES_TEXT_TYPE": 1,
    }
