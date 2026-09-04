from app.services.generation_standards import band_profile, grade_requirements, standard_prompt


def test_grades_map_to_three_separate_band_profiles():
    assert [band_profile(grade)["id"] for grade in range(1, 7)] == [
        "beginner", "beginner", "intermediate", "intermediate", "advanced", "advanced"
    ]


def test_beginner_profile_keeps_registered_modifiers_as_exceptions():
    policy = " ".join(band_profile(1)["vocabulary_and_style"])
    assert "등록 관형어·형용사·부사는 모두 허용" in policy


def test_each_grade_prompt_contains_its_band_validation_focus():
    for grade in range(1, 7):
        prompt = standard_prompt(grade, "reading")
        profile = band_profile(grade)
        assert f"구간 프로필: {profile['label']}" in prompt
        assert profile["validation_focus"][0] in prompt


def test_topik_ii_calibrated_passage_lengths_are_compact_and_progressive():
    assert [grade_requirements(grade)["passage_chars"] for grade in range(3, 7)] == [
        [220, 300], [280, 400], [380, 520], [500, 700]
    ]
    for grade in range(3, 7):
        prompt = standard_prompt(grade, "reading")
        assert "지문 목표 길이" in prompt
        assert "분량을 채우기 위한 새 사례·배경 설명은 추가하지 않음" in prompt
