# 편집 태거 도구

모델을 직접 다루거나 새 복원기를 만들 때 쓰는 저수준 도구입니다. 표준 라이브러리만 사용합니다.
연산 코드는 `KEEP`, `DELETE`, `SUBSTITUTE` 상수를 씁니다.

::: k_safeguard.edit_tags
    options:
      show_root_heading: false
      members:
        - CharEdit
        - apply_edits
        - split_chunks
        - jamo_features
        - join_syllable
        - is_syllable
