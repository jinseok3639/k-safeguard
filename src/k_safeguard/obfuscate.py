"""한글 표기 난독화 생성기. 정규화기를 시험하거나 학습·평가 데이터를 만들 때 쓴다.

모든 변환의 규약은 `(text, intensity=1.0, seed=0) -> str`이다. `intensity`는 후보 자리 중
바꿀 비율이고, 각 변환은 진입 시 자기 `random.Random(seed)`를 새로 만들어 같은 입력이면 항상 같은
결과를 낸다. 표준 라이브러리만 쓴다.

```python
from k_safeguard.obfuscate import TRANSFORMS, tensify

tensify("시스템", seed=0)                       # "씨쓰템"
TRANSFORMS["jamo_decompose"]("안녕")            # "ㅇㅏㄴㄴㅕㅇ"
```

기본 Gateway와는 연결되지 않는 독립 도구다. 초성체(`chosung`)처럼 정규화기가 되돌리지 않는 기법도
가드레일·LLM 강건성 평가를 위해 함께 둔다.
"""

from __future__ import annotations

import functools
import json
import random
from pathlib import Path

from . import _phonology as PH
from ._phonology import CHO_INDEX, JONG_INDEX, JUNG_INDEX
from .edit_tags import is_syllable, join_syllable
from .normalization import COMPAT_CHO, COMPAT_JONG, COMPAT_JUNG, HANGUL_BASE

OBFUSCATOR_VERSION = "1.0.0"

ZWSP = "\u200b"

LAX_TO_TENSE = {"ㄱ": "ㄲ", "ㄷ": "ㄸ", "ㅂ": "ㅃ", "ㅅ": "ㅆ", "ㅈ": "ㅉ"}
# 겹받침 -> (앞 자음, 뒤로 넘어갈 자음). 읽어 -> 일거
COMPOUND_JONG = {
    "ㄳ": ("ㄱ", "ㅅ"), "ㄵ": ("ㄴ", "ㅈ"), "ㄶ": ("ㄴ", "ㅎ"), "ㄺ": ("ㄹ", "ㄱ"), "ㄻ": ("ㄹ", "ㅁ"), "ㄼ": ("ㄹ", "ㅂ"),
    "ㄽ": ("ㄹ", "ㅅ"), "ㄾ": ("ㄹ", "ㅌ"), "ㄿ": ("ㄹ", "ㅍ"), "ㅀ": ("ㄹ", "ㅎ"), "ㅄ": ("ㅂ", "ㅅ"),
}

_ONSET_IEUNG = CHO_INDEX["ㅇ"]
_VOWEL_I = JUNG_INDEX["ㅣ"]

# 연음에서 뒤 음절 초성으로 넘어갈 수 있는 단자음 종성. ㅇ은 넘어가지 않는다.
_SIMPLE_JONG_TO_CHO = {
    JONG_INDEX[j]: CHO_INDEX[j]
    for j in COMPAT_JONG
    if j and j in CHO_INDEX and j != "ㅇ"
}
# 겹받침: 앞 자음은 종성으로 남고 뒤 자음이 초성으로 넘어간다. 읽어 -> 일거
_COMPOUND_JONG_TO_CHO = {
    JONG_INDEX[j]: (JONG_INDEX[front], CHO_INDEX[back])
    for j, (front, back) in COMPOUND_JONG.items()
    if back in CHO_INDEX
}
# 구개음화: 종성 ㄷ/ㅌ + '이' -> 초성 ㅈ/ㅊ
_PALATAL = {JONG_INDEX["ㄷ"]: CHO_INDEX["ㅈ"], JONG_INDEX["ㅌ"]: CHO_INDEX["ㅊ"]}

# 종성 크래밍에 쓰는 받침 풀. 실제 한국어에서 흔한 단자음 받침으로 제한해
# "그럴듯하지만 틀린" 표기를 만든다.
_CRAM_JONG = tuple(JONG_INDEX[j] for j in ("ㄱ", "ㄴ", "ㄹ", "ㅁ", "ㅂ", "ㅅ", "ㅇ"))


def _split(char):
    """완성형 음절 -> (초성, 중성, 종성) 인덱스. 종성 0은 받침 없음."""
    code = ord(char) - HANGUL_BASE
    jung_jong = len(COMPAT_JUNG) * len(COMPAT_JONG)
    return code // jung_jong, (code % jung_jong) // len(COMPAT_JONG), code % len(COMPAT_JONG)


def _pick(text, intensity, rng):
    """intensity 비율만큼 음절 인덱스를 결정론적으로 선택."""
    idxs = [i for i, ch in enumerate(text) if is_syllable(ch)]
    k = round(len(idxs) * intensity)
    return set(rng.sample(idxs, k)) if k else set()


def _choose(sites, intensity, rng):
    """후보 위치 목록에서 intensity 비율만큼 고른다."""
    k = round(len(sites) * intensity)
    return set(rng.sample(sites, k)) if k else set()


def _syllables(text):
    """텍스트 -> 음절은 가변 [초,중,종] 리스트, 그 외 문자는 None."""
    return [list(_split(ch)) if is_syllable(ch) else None for ch in text]


def _rebuild(text, syl):
    return "".join(join_syllable(*s) if s else ch for ch, s in zip(text, syl))


def jamo_decompose(text, intensity=1.0, seed=0):
    """자모분해: 안녕 -> ㅇㅏㄴㄴㅕㅇ. 길이 보존 안 됨."""
    rng = random.Random(seed)
    pick = _pick(text, intensity, rng)
    out = []
    for i, ch in enumerate(text):
        if is_syllable(ch) and i in pick:
            c, j, t = _split(ch)
            out.append(COMPAT_CHO[c] + COMPAT_JUNG[j] + COMPAT_JONG[t])
        else:
            out.append(ch)
    return "".join(out)


def chosung(text, intensity=1.0, seed=0):
    """초성체: 안녕하세요 -> ㅇㄴㅎㅅㅇ. 음절당 1문자라 길이 보존."""
    rng = random.Random(seed)
    pick = _pick(text, intensity, rng)
    out = []
    for i, ch in enumerate(text):
        if is_syllable(ch) and i in pick:
            out.append(COMPAT_CHO[_split(ch)[0]])
        else:
            out.append(ch)
    return "".join(out)


def tensify(text, intensity=1.0, seed=0):
    """된소리/쌍자음화: 시스템 -> 씨스템 (초성 평음->경음). 길이 보존."""
    rng = random.Random(seed)
    cand = [
        i for i, ch in enumerate(text)
        if is_syllable(ch) and COMPAT_CHO[_split(ch)[0]] in LAX_TO_TENSE
    ]
    pick = _choose(cand, intensity, rng)
    out = []
    for i, ch in enumerate(text):
        if i in pick:
            c, j, t = _split(ch)
            out.append(join_syllable(CHO_INDEX[LAX_TO_TENSE[COMPAT_CHO[c]]], j, t))
        else:
            out.append(ch)
    return "".join(out)


def break_spacing(text, intensity=1.0, seed=0):
    """띄어쓰기 파괴. intensity>=0.5면 모든 공백 제거, 아니면 글자 사이 공백 삽입."""
    if intensity >= 0.5:
        return text.replace(" ", "")
    rng = random.Random(seed)
    pick = _pick(text, intensity, rng)
    out = []
    for i, ch in enumerate(text):
        out.append(ch)
        if i in pick:
            out.append(" ")
    return "".join(out)


def zwsp_inject(text, intensity=1.0, seed=0):
    """음절 사이 zero-width space 삽입 (토크나이저 교란)."""
    rng = random.Random(seed)
    pick = _pick(text, intensity, rng)
    out = []
    for i, ch in enumerate(text):
        out.append(ch)
        if i in pick:
            out.append(ZWSP)
    return "".join(out)


def liaison(text, intensity=1.0, seed=0):
    """연음: 받침을 뒤 음절 초성으로 넘겨 소리대로 표기. 먹을게 -> 머글게, 읽어 -> 일거.

    겹받침은 앞 자음을 종성에 남기고 뒤 자음만 넘긴다.
    음절 수가 안 변하므로 길이 보존.
    """
    rng = random.Random(seed)
    syl = _syllables(text)
    sites = [
        i for i in range(len(syl) - 1)
        if syl[i]
        and (syl[i][2] in _SIMPLE_JONG_TO_CHO or syl[i][2] in _COMPOUND_JONG_TO_CHO)
        and syl[i + 1]
        and syl[i + 1][0] == _ONSET_IEUNG
    ]
    for i in _choose(sites, intensity, rng):
        jong = syl[i][2]
        if jong in _COMPOUND_JONG_TO_CHO:
            keep, move = _COMPOUND_JONG_TO_CHO[jong]
            syl[i][2] = keep
        else:
            move = _SIMPLE_JONG_TO_CHO[jong]
            syl[i][2] = 0
        syl[i + 1][0] = move
    return _rebuild(text, syl)


def palatalize(text, intensity=1.0, seed=0):
    """구개음화: 받침 ㄷ/ㅌ + '이' -> ㅈ/ㅊ. 굳이 -> 구지, 같이 -> 가치. 길이 보존."""
    rng = random.Random(seed)
    syl = _syllables(text)
    sites = [
        i for i in range(len(syl) - 1)
        if syl[i] and syl[i][2] in _PALATAL
        and syl[i + 1] and syl[i + 1][0] == _ONSET_IEUNG and syl[i + 1][1] == _VOWEL_I
    ]
    for i in _choose(sites, intensity, rng):
        syl[i + 1][0] = _PALATAL[syl[i][2]]
        syl[i][2] = 0
    return _rebuild(text, syl)


def jongseong_cram(text, intensity=1.0, seed=0):
    """종성 크래밍: 받침에 불필요한 자음을 채워 넣는다. 안녕 -> 앉녕 식.

    받침 없는 음절에는 받침을 새로 넣고, 받침 있는 음절은 다른 단자음 받침으로 바꾼다.
    어느 쪽이든 음절 하나는 음절 하나로 남으므로 길이가 보존된다. 결과물이 문법적으로는
    정상인 한글 음절이라, 초성체의 호환 자모 같은 값싼 탐지 신호가 없는 것이 이 기법의 요점이다.
    """
    rng = random.Random(seed)
    cand = [i for i, ch in enumerate(text) if is_syllable(ch)]
    pick = _choose(cand, intensity, rng)
    out = []
    for i, ch in enumerate(text):
        if i not in pick:
            out.append(ch)
            continue
        c, j, t = _split(ch)
        options = [x for x in _CRAM_JONG if x != t]
        out.append(join_syllable(c, j, rng.choice(options)))
    return "".join(out)


def _adjacent_sites(syl, predicate):
    """앞뒤 음절 쌍에 predicate(앞, 뒤)가 참인 앞 음절 인덱스 목록."""
    return [
        i for i in range(len(syl) - 1)
        if syl[i] and syl[i + 1] and predicate(syl[i], syl[i + 1])
    ]


def _unary_sites(syl, predicate):
    """음절 하나만 보고 predicate(음절)이 참인 인덱스 목록."""
    return [i for i, s in enumerate(syl) if s and predicate(s)]


def liaison_correct(text, intensity=1.0, seed=0):
    """표준발음법을 지키는 연음. `liaison`과 달리 받침 ㅎ을 뒤로 넘기지 않고 탈락시킨다.

    좋아 -> 조아, 많아 -> 마나, 싫어 -> 시러 (제12항 4). 나머지 받침은 `liaison`과 같다.

    `liaison`이 만드는 조하·실허 같은 표기도 실제 오타로 흔히 나타나므로 둘을 나란히 둔다.
    "표준 발음형"과 "오타형"을 각각 다룰 수 있다.
    """
    rng = random.Random(seed)
    syl = _syllables(text)
    sites = _adjacent_sites(
        syl,
        lambda a, b: b[0] == _ONSET_IEUNG and (
            a[2] in PH.H_CODA_BEFORE_VOWEL_IDX
            or a[2] in _SIMPLE_JONG_TO_CHO
            or a[2] in _COMPOUND_JONG_TO_CHO
        ),
    )
    for i in sorted(_choose(sites, intensity, rng)):
        jong = syl[i][2]
        if jong in PH.H_CODA_BEFORE_VOWEL_IDX:
            keep, move = PH.H_CODA_BEFORE_VOWEL_IDX[jong]
            syl[i][2] = keep
            if move is not None:
                syl[i + 1][0] = move
        elif jong in _COMPOUND_JONG_TO_CHO:
            keep, move = _COMPOUND_JONG_TO_CHO[jong]
            syl[i][2] = keep
            syl[i + 1][0] = move
        else:
            syl[i + 1][0] = _SIMPLE_JONG_TO_CHO[jong]
            syl[i][2] = 0
    return _rebuild(text, syl)


def h_deletion(text, intensity=1.0, seed=0):
    """ㅎ 탈락만 따로. 종성 ㅎ/ㄶ/ㅀ + 모음 -> ㅎ이 사라진다 (제12항 4).

    좋아 -> 조아, 많아 -> 마나, 싫어 -> 시러, 낳은 -> 나은. 길이 보존.
    """
    rng = random.Random(seed)
    syl = _syllables(text)
    sites = _adjacent_sites(
        syl, lambda a, b: a[2] in PH.H_CODA_BEFORE_VOWEL_IDX and b[0] == _ONSET_IEUNG
    )
    for i in sorted(_choose(sites, intensity, rng)):
        keep, move = PH.H_CODA_BEFORE_VOWEL_IDX[syl[i][2]]
        syl[i][2] = keep
        if move is not None:
            syl[i + 1][0] = move
    return _rebuild(text, syl)


def aspirate(text, intensity=1.0, seed=0):
    """격음화(유기음화). ㅎ과 평음이 만나 거센소리로 축약된다 (제12항 1). 길이 보존.

    양방향이다.
    - 종성 ㅎ계열 + 초성 평음: 놓고 -> 노코, 좋다 -> 조타, 많지 -> 만치, 닳지 -> 달치
    - 종성 평음 + 초성 ㅎ:   국화 -> 구콰, 맏형 -> 마텽, 좁히다 -> 조피다, 밝히다 -> 발키다
    """
    rng = random.Random(seed)
    syl = _syllables(text)
    cho_h = CHO_INDEX["ㅎ"]
    sites = _adjacent_sites(
        syl,
        lambda a, b: (
            (a[2] in PH.H_CODA_RESIDUE_IDX and b[0] in PH.H_FOLLOWING_ONSET_IDX)
            or (a[2] in PH.CODA_PLUS_H_IDX and b[0] == cho_h)
        ),
    )
    for i in sorted(_choose(sites, intensity, rng)):
        jong, nxt = syl[i][2], syl[i + 1][0]
        if jong in PH.H_CODA_RESIDUE_IDX and nxt in PH.H_FOLLOWING_ONSET_IDX:
            syl[i][2] = PH.H_CODA_RESIDUE_IDX[jong]
            syl[i + 1][0] = PH.H_FOLLOWING_ONSET_IDX[nxt]
        else:
            keep, asp = PH.CODA_PLUS_H_IDX[jong]
            syl[i][2] = keep
            syl[i + 1][0] = asp
    return _rebuild(text, syl)


def vowel_confuse(text, intensity=1.0, seed=0):
    """모음 혼동 표기. ㅐ/ㅔ, ㅒ/ㅖ, ㅚ/ㅙ/ㅞ, ㅢ/ㅣ/ㅔ 를 서로 바꾼다. 길이 보존.

    표준발음법 조항이 아니라 실제 화자가 구분 못 하거나 자주 틀리는 **표기 혼동**이다.
    """
    rng = random.Random(seed)
    syl = _syllables(text)
    sites = _unary_sites(syl, lambda s: s[1] in PH.CONFUSABLE_JUNG_INDICES)
    for i in sorted(_choose(sites, intensity, rng)):
        syl[i][1] = rng.choice(PH.VOWEL_CONFUSION_IDX[syl[i][1]])
    return _rebuild(text, syl)


def coda_neutralize(text, intensity=1.0, seed=0):
    """평파열음화(음절의 끝소리 규칙). 종성을 7종성으로 중화한다 (제8·9항). 길이 보존.

    부엌 -> 부억, 옷 -> 옫, 빛 -> 빋, 앞 -> 압.
    ㅅㅆㅈㅊㅌㅎ이 전부 ㄷ으로 가는 **다대일** 사상이라 원리적으로 되돌릴 수 없는 정보가 생긴다.
    """
    rng = random.Random(seed)
    syl = _syllables(text)
    sites = _unary_sites(syl, lambda s: s[2] in PH.CODA_NEUTRALIZE_IDX)
    for i in sorted(_choose(sites, intensity, rng)):
        syl[i][2] = PH.CODA_NEUTRALIZE_IDX[syl[i][2]]
    return _rebuild(text, syl)


def cluster_reduce(text, intensity=1.0, seed=0):
    """자음군 단순화. 겹받침 둘 중 하나만 남긴다 (제10·11항). 길이 보존.

    값 -> 갑, 넋 -> 넉, 닭 -> 닥, 삶 -> 삼, 여덟 -> 여덜.
    """
    rng = random.Random(seed)
    syl = _syllables(text)
    sites = _unary_sites(syl, lambda s: s[2] in PH.CLUSTER_REDUCE_IDX)
    for i in sorted(_choose(sites, intensity, rng)):
        syl[i][2] = PH.CLUSTER_REDUCE_IDX[syl[i][2]]
    return _rebuild(text, syl)


def nasalize(text, intensity=1.0, seed=0):
    """비음화 (제18·19항). 길이 보존.

    - 파열음의 비음화: 국물 -> 궁물, 닫는 -> 단는, 밥물 -> 밤물
    - ㄹ의 비음화:     종로 -> 종노, 강릉 -> 강능, 담력 -> 담녁
    - 상호 비음화:     백리 -> 뱅니, 섭리 -> 섬니
    """
    rng = random.Random(seed)
    syl = _syllables(text)

    def is_site(a, b):
        if a[2] in PH.CODA_TO_NASAL_IDX and b[0] in PH.NASAL_ONSET_INDICES:
            return True                                   # 파열음의 비음화
        if b[0] == PH.CHO_R:
            return (
                a[2] in PH.NASAL_CODA_BEFORE_R_INDICES     # ㄹ의 비음화
                or a[2] in PH.CODA_TO_NASAL_IDX            # 상호 비음화
            )
        return False

    for i in sorted(_choose(_adjacent_sites(syl, is_site), intensity, rng)):
        jong, nxt = syl[i][2], syl[i + 1][0]
        if nxt == PH.CHO_R:
            syl[i + 1][0] = PH.CHO_N
            if jong in PH.CODA_TO_NASAL_IDX:
                syl[i][2] = PH.CODA_TO_NASAL_IDX[jong]
        else:
            syl[i][2] = PH.CODA_TO_NASAL_IDX[jong]
    return _rebuild(text, syl)


def lateralize(text, intensity=1.0, seed=0):
    """유음화 (제20항). ㄴ과 ㄹ이 만나면 ㄹㄹ이 된다. 길이 보존.

    신라 -> 실라, 난로 -> 날로, 칼날 -> 칼랄, 설날 -> 설랄, 권력 -> 궐력.
    """
    rng = random.Random(seed)
    syl = _syllables(text)
    sites = _adjacent_sites(
        syl,
        lambda a, b: (a[2] == PH.JONG_N and b[0] == PH.CHO_R)
        or (a[2] == PH.JONG_R and b[0] == PH.CHO_N),
    )
    for i in sorted(_choose(sites, intensity, rng)):
        if syl[i][2] == PH.JONG_N:
            syl[i][2] = PH.JONG_R          # 신라 -> 실라
        else:
            syl[i + 1][0] = PH.CHO_R       # 칼날 -> 칼랄
    return _rebuild(text, syl)


def tensify_rule(text, intensity=1.0, seed=0):
    """규칙 경음화 (제23~28항). 장애음 종성 뒤 평음 초성만 경음이 된다. 길이 보존.

    국밥 -> 국빱, 학교 -> 학꾜, 먹다 -> 먹따, 옷고름 -> 옫꼬름.

    기존 `tensify`가 문맥과 무관하게 아무 평음 초성이나 바꾸는 것과 대비된다 — 이쪽은
    실제 한국어 화자가 그렇게 **발음하는** 자리만 골라서 표기에 반영한다.
    """
    rng = random.Random(seed)
    syl = _syllables(text)
    sites = _adjacent_sites(
        syl,
        lambda a, b: a[2] in PH.OBSTRUENT_CODA_INDICES
        and b[0] in PH.TENSIFIABLE_ONSET_INDICES,
    )
    for i in sorted(_choose(sites, intensity, rng)):
        syl[i + 1][0] = PH.LAX_TO_TENSE_ONSET_IDX[syl[i + 1][0]]
    return _rebuild(text, syl)


# 반모음 첨가(KOTOX 2-1): 단모음에 y계·w계 반모음을 붙인다.
_GLIDE = {
    "ㅏ": ("ㅑ", "ㅘ"), "ㅓ": ("ㅕ", "ㅝ"), "ㅗ": ("ㅛ",), "ㅜ": ("ㅠ",),
    "ㅐ": ("ㅒ", "ㅙ"), "ㅔ": ("ㅖ", "ㅞ"), "ㅣ": ("ㅟ",),
}
_GLIDE_IDX = {JUNG_INDEX[k]: tuple(JUNG_INDEX[v] for v in vs) for k, vs in _GLIDE.items()}

# 초성 첨가(KOTOX 2-3): 소리 없는 초성 ㅇ 자리에 넣는 자음. ㄴ은 실제 ㄴ첨가(솜이불 -> 솜니불)에서 온다.
_ADDED_ONSET = tuple(CHO_INDEX[c] for c in ("ㅎ", "ㄴ"))

# 기호·이모티콘 삽입(KOTOX 13-2)에 쓰는 보이는 문자.
_SYMBOLS = (".", ",", "*", "~", "^", "-", "_", "/", "!", "°", "♡", "♥", "☆", "★", "♪", "ㅋ", "ㅎ", "😂", "👍")

# 음절 늘이기(KoNTe 음절 확장): 이중모음을 두 음절로 풀어 쓴다. 화장실 -> 호아장실·호와장실
_SPLIT_VOWEL = {
    "ㅘ": "ㅗ", "ㅙ": "ㅗ", "ㅚ": "ㅗ", "ㅝ": "ㅜ", "ㅞ": "ㅜ", "ㅟ": "ㅜ", "ㅢ": "ㅡ",
    "ㅑ": "ㅣ", "ㅕ": "ㅣ", "ㅛ": "ㅣ", "ㅠ": "ㅣ", "ㅒ": "ㅣ", "ㅖ": "ㅣ",
}
_SPLIT_REST = {"ㅘ": "ㅏ", "ㅙ": "ㅐ", "ㅚ": "ㅣ", "ㅝ": "ㅓ", "ㅞ": "ㅔ", "ㅟ": "ㅣ", "ㅢ": "ㅣ"}

# 닮은 글자 사전: KOTOX(MIT, https://github.com/leeyejin1231/KOTOX)의 rules/iconic_dictionary.json.
# 라이선스는 같은 폴더의 KOTOX_LICENSE.
_ICONIC_PATH = Path(__file__).resolve().parent / "data" / "iconic_dictionary.json"
_KOTOX_ERRATA = {("ㄹ", "㉢")}   # ㉢은 ㄷ이다. 사전의 오기
_VERTICAL_VOWELS = frozenset("ㅗㅛㅜㅠㅡㅚㅙㅞㅟㅝㅘ")   # 자음이 모음 위에 얹히는 모양이라 자음만 바꾸면 못 읽는다


def _has_hangul(s):
    return any(is_syllable(c) or "ㄱ" <= c <= "ㆎ" for c in s)


@functools.lru_cache(maxsize=1)
def _iconic():
    """사전을 두 갈래로 나눈다.

    foreign = 한글 -> 비한글(ㄱ -> 7, 가 -> ㉮). 되돌릴 답이 하나다.
    hangul = 한글 -> 한글(대 -> 머, 부부 -> 쀼). 양쪽이 실제 글자라 정상 문장 오변경 위험이 있다.
    """
    raw = json.loads(_ICONIC_PATH.read_text(encoding="utf-8"))

    def split_values(table):
        foreign, hangul = {}, {}
        for key, values in table.items():
            values = [v for v in values if (key, v) not in _KOTOX_ERRATA]
            if f := tuple(v for v in values if not _has_hangul(v)):
                foreign[key] = f
            if h := tuple(v for v in values if _has_hangul(v)):
                hangul[key] = h
        return foreign, hangul

    consonant, _ = split_values(raw["consonant_dict"])
    vowel, _ = split_values(raw["vowel_dict"])
    syllable, yamin = split_values(raw["yamin_dict"])
    return {
        "consonant": consonant, "vowel": vowel, "syllable": syllable,
        "hangul": {**yamin, **raw["compression_dict"]},
    }


def semivowel_insert(text, intensity=1.0, seed=0):
    """반모음 첨가: 단모음에 반모음을 붙인다. 거품 -> 궈퓸, 해줘 -> 햬줘. 길이 보존."""
    rng = random.Random(seed)
    syl = _syllables(text)
    sites = [i for i, s in enumerate(syl) if s and s[1] in _GLIDE_IDX]
    for i in sorted(_choose(sites, intensity, rng)):
        syl[i][1] = rng.choice(_GLIDE_IDX[syl[i][1]])
    return _rebuild(text, syl)


def initial_insert(text, intensity=1.0, seed=0):
    """초성 첨가: 초성 ㅇ 자리에 자음을 넣는다. 많이 -> 많히, 솜이불 -> 솜니불. 길이 보존."""
    rng = random.Random(seed)
    syl = _syllables(text)
    sites = [i for i, s in enumerate(syl) if s and s[0] == _ONSET_IEUNG]
    for i in sorted(_choose(sites, intensity, rng)):
        syl[i][0] = rng.choice(_ADDED_ONSET)
    return _rebuild(text, syl)


def jamo_copy(text, intensity=1.0, seed=0):
    """자모 복제(yu2024 COPY): 이웃 자모를 한 번 더 쓴다. 길이 보존 안 됨.

    - 받침 복제: 받침 없는 음절에 다음 음절의 초성을 받침으로 넣는다. 쓰레기 -> 쓸레기
    - 모음 늘이기: 음절 뒤에 같은 모음의 'ㅇ+모음' 음절을 붙인다. 쓰레기 -> 쓰레에기
    받침 복제가 가능한 자리는 둘 중 하나를 고르고, 아니면 모음 늘이기를 한다.
    """
    rng = random.Random(seed)
    syl = _syllables(text)

    def copied_coda(i):
        nxt = syl[i + 1] if i + 1 < len(syl) else None
        if syl[i][2] or not nxt or nxt[0] == _ONSET_IEUNG:
            return None
        return JONG_INDEX.get(COMPAT_CHO[nxt[0]])   # ㄸ·ㅃ·ㅉ은 받침이 될 수 없다

    pick = _choose([i for i, s in enumerate(syl) if s], intensity, rng)
    out = []
    for i, (ch, s) in enumerate(zip(text, syl)):
        if i not in pick:
            out.append(ch)
            continue
        coda = copied_coda(i)
        if coda is not None and rng.random() < 0.5:
            out.append(join_syllable(s[0], s[1], coda))
        else:
            out.append(ch + join_syllable(_ONSET_IEUNG, s[1], 0))
    return "".join(out)


def symbol_insert(text, intensity=1.0, seed=0):
    """기호·이모티콘 삽입: 음절 뒤에 보이는 기호를 끼운다. 돈을 -> 돈°을. 길이 보존 안 됨.

    zwsp_inject의 보이는 판이다.
    """
    rng = random.Random(seed)
    pick = _pick(text, intensity, rng)
    out = []
    for i, ch in enumerate(text):
        out.append(ch)
        if i in pick:
            out.append(rng.choice(_SYMBOLS))
    return "".join(out)


def syllable_extend(text, intensity=1.0, seed=0):
    """음절 늘이기: 이중모음 음절을 두 음절로 푼다. 화장실 -> 호와장실, 뭐야 -> 무어야. 길이 보존 안 됨.

    뒤 음절의 모음은 원래 이중모음(호와)과 남는 단모음(호아) 중 하나를 고른다. 받침은 뒤 음절로 간다.
    """
    rng = random.Random(seed)
    syl = _syllables(text)
    sites = [i for i, s in enumerate(syl) if s and COMPAT_JUNG[s[1]] in _SPLIT_VOWEL]
    pick = _choose(sites, intensity, rng)
    out = []
    for i, (ch, s) in enumerate(zip(text, syl)):
        if i not in pick:
            out.append(ch)
            continue
        vowel = COMPAT_JUNG[s[1]]
        rest = rng.choice((vowel, _SPLIT_REST[vowel])) if vowel in _SPLIT_REST else vowel
        out.append(join_syllable(s[0], JUNG_INDEX[_SPLIT_VOWEL[vowel]], 0) + join_syllable(_ONSET_IEUNG, JUNG_INDEX[rest], s[2]))
    return "".join(out)


def _foreign_options(ch):
    """음절 하나를 닮은 비한글로 바꾸는 후보들. 바꾸지 않는 자모는 호환 자모로 풀어 쓴다."""
    table = _iconic()
    c, j, t = _split(ch)
    cho, jung, jong = COMPAT_CHO[c], COMPAT_JUNG[j], COMPAT_JONG[t]
    options = list(table["syllable"].get(ch, ()))
    if jung + jong in table["vowel"]:
        options += [cho + v for v in table["vowel"][jung + jong]]
    elif not jong and jung in table["vowel"]:
        options += [cho + v for v in table["vowel"][jung]]
    if cho in table["consonant"] and jung not in _VERTICAL_VOWELS:
        options += [v + jung + jong for v in table["consonant"][cho]]
    return options


def lookalike_foreign(text, intensity=1.0, seed=0):
    """닮은 비한글 문자: 음절이나 그 자모를 모양이 닮은 비한글로 바꾼다. 가 -> 7ㅏ·㉮, 네 -> ㄴ¶.

    사전은 KOTOX iconic_dictionary(5-2 consonant_swap과 같은 원천). 길이 보존 안 됨.
    """
    rng = random.Random(seed)
    sites = [i for i, ch in enumerate(text) if is_syllable(ch) and _foreign_options(ch)]
    pick = _choose(sites, intensity, rng)
    return "".join(rng.choice(_foreign_options(ch)) if i in pick else ch for i, ch in enumerate(text))


def lookalike_hangul(text, intensity=1.0, seed=0):
    """닮은 한글(야민정음): 모양이 닮은 다른 한글로 바꾼다. 대 -> 머, 명 -> 띵, 부부 -> 쀼.

    사전은 KOTOX iconic_dictionary의 한글끼리 쌍과 압축(compression). 두 음절 압축이 먼저 걸린다.
    """
    rng = random.Random(seed)
    table = _iconic()["hangul"]
    sites, i = [], 0
    while i < len(text):
        for width in (2, 1):
            if text[i:i + width] in table and len(text[i:i + width]) == width:
                sites.append((i, width))
                i += width
                break
        else:
            i += 1
    pick = dict(sorted(_choose(sites, intensity, rng)))
    out, i = [], 0
    while i < len(text):
        if i in pick:
            out.append(rng.choice(table[text[i:i + pick[i]]]))
            i += pick[i]
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


TRANSFORMS = {
    "jamo_decompose": jamo_decompose,
    "chosung": chosung,
    "tensify": tensify,
    "break_spacing": break_spacing,
    "zwsp_inject": zwsp_inject,
    "liaison": liaison,
    "palatalize": palatalize,
    "jongseong_cram": jongseong_cram,
    "liaison_correct": liaison_correct,
    "h_deletion": h_deletion,
    "aspirate": aspirate,
    "vowel_confuse": vowel_confuse,
    "coda_neutralize": coda_neutralize,
    "cluster_reduce": cluster_reduce,
    "nasalize": nasalize,
    "lateralize": lateralize,
    "tensify_rule": tensify_rule,
    "semivowel_insert": semivowel_insert,
    "initial_insert": initial_insert,
    "jamo_copy": jamo_copy,
    "symbol_insert": symbol_insert,
    "syllable_extend": syllable_extend,
    "lookalike_foreign": lookalike_foreign,
    "lookalike_hangul": lookalike_hangul,
}

# 'phonetic' = 음운·철자를 바꾸는 변형, 'visual' = 글자 모양이나 배치를 바꾸는 변형.
FAMILY = {
    "jamo_decompose": "visual",
    "chosung": "visual",
    "break_spacing": "visual",
    "zwsp_inject": "visual",
    "tensify": "phonetic",
    "liaison": "phonetic",
    "palatalize": "phonetic",
    "jongseong_cram": "phonetic",
    "liaison_correct": "phonetic",
    "h_deletion": "phonetic",
    "aspirate": "phonetic",
    "vowel_confuse": "phonetic",
    "coda_neutralize": "phonetic",
    "cluster_reduce": "phonetic",
    "nasalize": "phonetic",
    "lateralize": "phonetic",
    "tensify_rule": "phonetic",
    "semivowel_insert": "phonetic",
    "initial_insert": "phonetic",
    "jamo_copy": "phonetic",
    "syllable_extend": "phonetic",
    "symbol_insert": "visual",
    "lookalike_foreign": "visual",
    "lookalike_hangul": "visual",
}

# 입력과 출력의 문자 수가 항상 같은 변환.
LENGTH_PRESERVING = frozenset(
    {
        "chosung", "tensify", "liaison", "palatalize", "jongseong_cram",
        "liaison_correct", "h_deletion", "aspirate", "vowel_confuse",
        "coda_neutralize", "cluster_reduce", "nasalize", "lateralize",
        "tensify_rule", "semivowel_insert", "initial_insert",
    }
)

# 표준발음법 조항 근거가 있는 기법 -> 조항 번호. 보고서에서 근거를 밝히는 데 쓴다.
# vowel_confuse는 조항이 아니라 표기 혼동이므로 여기 없다.
STANDARD_PRONUNCIATION_CLAUSE = {
    "liaison": "제13·14항",
    "liaison_correct": "제13·14항 + 제12항 4",
    "h_deletion": "제12항 4",
    "aspirate": "제12항 1",
    "palatalize": "제17항",
    "coda_neutralize": "제8·9항",
    "cluster_reduce": "제10·11항",
    "nasalize": "제18·19항",
    "lateralize": "제20항",
    "tensify_rule": "제23~28항",
}


def obfuscate(text, technique, intensity=1.0, seed=0):
    """`technique` 이름으로 변환 하나를 건다."""
    try:
        transform = TRANSFORMS[technique]
    except KeyError:
        raise ValueError(
            f"지원하지 않는 기법입니다: {technique!r} (사용 가능: {', '.join(sorted(TRANSFORMS))})"
        ) from None
    return transform(text, intensity, seed)
