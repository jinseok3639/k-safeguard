# 한국어 난독화 방법 조사

> 조사일: 2026-08-05
>
> 상태: 난독화 생성기 설계 전 기술 조사
>
> 적용 범위: 한국어 텍스트 입력의 표기·음운 난독화와 가드레일 강건성 평가

## 1. 결론

한국어 난독화는 하나의 기법이 아니라 최소 여섯 계열로 나눠야 한다.

1. **Unicode·인코딩 변형**: 결합 자모, 호환 자모, 폭 변형, 투명문자
2. **자모·정보 축약**: 자모 분해, 초성체, 종성 추가·교체
3. **음운 표기 변형**: 초성·중성·종성의 유사음 치환, 연음, 구개음화, 발음대로 적기
4. **분절·순서 변형**: 띄어쓰기 삽입·삭제, 음절 재배열
5. **시각·교차 문자권 변형**: 닮은꼴 한글, 회전형, 한자·라틴·기호 치환
6. **번역·화용 변형**: 로마자 음차, 의미 번역, 코드스위칭, 이모지·기호 삽입

k-safeguard의 주력은 3번 **음운 표기 변형**이어야 한다. 1번은 표준 정규화로 처리할 수 있는
대조군이고, 2·4·5번은 복원 난이도와 실제 사용성이 서로 달라 별도 family로 집계해야 한다.
6번은 규칙 기반 난독화 범위를 넘어 문맥·다국어 이해가 필요하므로 후속 트랙이 적절하다.

공개 연구도 이 구분을 뒷받침한다.

- Cho와 Kim은 한국 온라인 난독화를 형태, 형태·음운, 시각, 의미 전략으로 분류하고, 사용 목적을
  tricks·memes·fillers·codes로 구분했다. 특히 Airbnb 후기, 야민정음, 필터 우회 표현은 같은
  변환처럼 보여도 목적과 독자가 다르다고 지적한다
  ([ACL Anthology](https://aclanthology.org/2021.wnut-1.7/)).
- PHISH는 음절을 자모로 분해한 뒤 IPA와 표준 발음 규칙에 따라 유사한 자모 1~2개를 치환하고,
  공격 비율을 "변경 가능한 음절 중 실제 변경한 음절 비율"로 정의했다
  ([논문](https://arxiv.org/abs/2505.21380)).
- KOTOX는 한국어 난독화를 음운·시각·음차·통사·화용의 5개 접근, 17개 규칙으로 정리하고
  원문과 난독화문이 정렬된 데이터셋을 공개했다
  ([논문](https://arxiv.org/abs/2510.10961),
  [코드](https://github.com/leeyejin1231/KOTOX),
  [데이터](https://huggingface.co/datasets/ssgyejin/KOTOX)).

이 문서의 예시는 변환 원리를 설명하기 위한 무해 문장만 사용한다. 난독화는 암호화가 아니며,
사람이나 모델이 원문을 추론할 수 있다.

## 2. 용어와 분류 기준

### 2.1 난독화와 자연스러운 비표준 표기

본 프로젝트에서 **난독화(obfuscation)** 는 원래 의도를 대체로 유지하면서 입력의 표면형을 바꾸는
변환이다. 공격자가 필터를 피하려고 의도적으로 만든 표기뿐 아니라, 실사용에서 우연히 같은 형태가
되는 오타·통신체도 모델 관점에서는 같은 강건성 문제를 만든다.

다만 데이터에는 생성 목적을 별도 필드로 남긴다.

| `origin` | 의미 |
|---|---|
| `adversarial` | 필터·번역기·분류기 회피가 명시적 목적 |
| `conventional` | 초성체, 통신체, 야민정음처럼 공동체 관습으로 정착 |
| `synthetic` | 평가를 위해 알고리즘이 생성 |
| `accidental` | 입력기·인코딩·오타로 우연히 발생 |

동일 표면형이라도 목적을 혼합하면 실제 공격 분포와 합성 benchmark를 구분할 수 없다.

### 2.2 변환을 나누는 네 축

각 기법은 family 이름만 저장하지 말고 다음 네 속성을 함께 기록해야 한다.

- **단위**: code point / 자모 / 음절 / 형태소 / 어절 / 문장
- **보존 신호**: Unicode 동등성 / 시각 / 발음 / 문맥 의미
- **정보 손실**: 가역 / 후보가 여러 개인 lossy / 원문 복원 불가능
- **복원 수단**: 표준 정규화 / 규칙 / 사전·형태소 분석 / G2P·언어모델

예를 들어 자모 분해와 초성체는 모두 자모를 사용하지만 전자는 대부분의 정보를 보존하고 후자는
중성·종성을 삭제한다. 같은 family로 합치면 방어 난이도를 설명할 수 없다.

## 3. 방법별 taxonomy

### 3.1 요약표

| ID | family | 방법 | 무해 예시 | 손실성 | NFKC만으로 복원 | 프로젝트 우선순위 |
|---|---|---|---|---|---|---|
| U1 | `unicode` | 결합 자모 분해(NFD형) | `안` → `안` | 가역 | 가능 | 대조군 P1 |
| U2 | `unicode` | 호환 자모 분해 | `안` → `ㅇㅏㄴ` | 위치 모호 | 불완전 | 대조군 P1 |
| U3 | `unicode` | 투명·format 문자 삽입 | `한글` → `한​글` | 대체로 가역 | 불가 | 대조군 P1 |
| U4 | `unicode` | 호환·폭 변형 | `ABC` → `ＡＢＣ` | 대체로 가역 | 가능 | 대조군 P2 |
| O1 | `orthographic` | 초성체 | `한국어` → `ㅎㄱㅇ` | 매우 lossy | 불가 | 진단 P1 |
| O2 | `orthographic` | 종성 삽입·교체 | `한국어` → `핝국억` | lossy | 불가 | 주력 후보 P0 |
| P1 | `phonological` | 초성 유사음 치환 | `한국` → `한꾹` | lossy | 불가 | 주력 P0 |
| P2 | `phonological` | 중성 유사음 치환 | `해` → `헤` | lossy | 불가 | 주력 P0 |
| P3 | `phonological` | 연음·재음절화 | `먹을게` → `머글게` | lossy | 불가 | 주력 P0 |
| P4 | `phonological` | 구개음화 표기 | `굳이` → `구지` | lossy | 불가 | 주력 P0 |
| P5 | `phonological` | 전체 발음 표기(G2P) | `국밥` → `국빱` | lossy | 불가 | 진단 P1 |
| S1 | `segmentation` | 공백 삽입·삭제 | `한국어 테스트` → `한국어테스트` | 대체로 가역 | 불가 | 대조군 P1 |
| S2 | `segmentation` | 음절 재배열 | `오랜만에` → `오만랜에` | lossy | 불가 | 후속 P2 |
| V1 | `visual` | 한글 닮은꼴·회전형 | `귀엽다` → `커엽다` | lossy | 불가 | 대조군 P1 |
| V2 | `cross_script` | 한자·라틴·기호 치환 | `수상해` → `水상해` | 사전 의존 | 대부분 불가 | 후속 P2 |
| T1 | `transliteration` | 로마자·키보드 음차 | `안녕` → `dkssud` | 규칙별 상이 | 불가 | 후속 P2 |
| T2 | `transliteration` | 의미 번역·재음차 | `가지 마` → 다국어 혼용 | 매우 lossy | 불가 | 별도 트랙 P3 |
| R1 | `pragmatic` | 기호·이모지 삽입 | `정말 좋아` → `정말 ♡ 좋아` | 대체로 가역 | 불가 | 대조군 P2 |

우선순위는 이 프로젝트의 차별성과 실험 효율을 기준으로 한 제안이다. 실제 적용 여부는 파일럿에서
`changed`, 의미 보존율, clean 차단율과 회피율을 확인한 뒤 결정한다.

### 3.2 Unicode·인코딩 변형

#### U1. 결합 자모 분해

완성형 한글 음절 U+AC00~U+D7A3을 초성 U+1100대, 중성 U+1160대, 종성 U+11A8대로 분해한다.
Unicode에서 한글 음절 분해는 canonical decomposition이므로 NFC로 다시 조합할 수 있다.
[Unicode UAX #15](https://www.unicode.org/reports/tr15/)는 Hangul 분해·조합을 정규화 알고리즘의
일부로 규정한다.

- 장점: 완전 결정론적이고 의미가 보존된다.
- 공격 효과: 화면은 같거나 유사하지만 code point와 tokenizer 입력이 달라질 수 있다.
- 방어: NFC를 가장 먼저 적용한다.
- 평가 역할: 정규화기가 당연히 복구해야 하는 sanity check다.

#### U2. 호환 자모 분해

`ㅇㅏㄴ`처럼 U+3130대 Hangul Compatibility Jamo를 이어 붙인다. 결합 자모와 달리 각 자음이
초성인지 종성인지 문자열만으로 확정되지 않는다.

2026-08-05에 .NET Unicode 정규화로 확인한 결과는 다음과 같다.

| 입력 | NFKC 결과 | 해석 |
|---|---|---|
| `안` | `안` | 결합 자모는 완성형으로 복원 |
| `ㅇㅏㄴ` | `아ᄂ` | 마지막 `ㄴ`이 종성이 아니라 초성 자모로 남음 |

따라서 "자모 분해는 NFKC면 모두 복원된다"고 쓰면 안 된다. 호환 자모열은 한글 오토마타나 위치
추론이 추가로 필요하다.

#### U3. 투명문자와 format control

U+200B ZERO WIDTH SPACE, U+200C ZWNJ, U+200D ZWJ, U+2060 WORD JOINER, U+FEFF 등을 글자 사이에
삽입한다. 눈에는 거의 보이지 않지만 tokenizer나 문자열 비교에서는 별도 code point다.

- NFKC는 `한<U+200B>글`의 U+200B를 제거하지 않았다.
- Unicode는 U+200B와 여러 format 문자를 `Default_Ignorable_Code_Point` 계열로 설명한다
  ([Unicode FAQ](https://www.unicode.org/faq/unsup_char.html)).
- UTS #39는 default-ignorable 문자와 mixed-script confusable을 별도 보안 문제로 다룬다
  ([UTS #39](https://www.unicode.org/reports/tr39/)).

한국어 입력에서는 ZWJ/ZWNJ가 정상 맞춤법에 필요하지 않지만, 전 언어 공용 서비스가 무조건 삭제하면
다른 문자권의 정당한 표기를 훼손할 수 있다. 게이트웨이는 언어·script 문맥과 원문 보존 로그를 함께
사용해야 한다.

현재 무손실 정규화 코어는 한글·자모와 인접한 U+200B만 제거한다. U+200C ZWNJ, U+200D ZWJ,
U+2060 WORD JOINER, U+FEFF BOM과 U+00AD SOFT HYPHEN은 범용 입력 훼손을 피하기 위해 한글·자모
사이에 있어도 보존한다. 이 문자들의 삭제가 필요하다면 원문 보존 로그를 갖춘 별도 opt-in 정책으로
다뤄야 한다.

#### U4. 호환 문자·폭 변형

전각 라틴 문자, 원문자, 호환 단위 등을 사용한다. 예를 들어 NFKC는 `ＡＢＣ`를 `ABC`, `㈜`를
`(주)`로 바꾼다. 이 family는 NFKC 효과를 검증하기 좋지만 한국어 음운 난독화의 핵심 증거로
사용해서는 안 된다.

### 3.3 자모·정보 축약

#### O1. 초성체

각 음절의 초성만 남긴다. `한국어`는 `ㅎㄱㅇ`이 된다. 문맥이 짧거나 후보가 많으면 원문을 하나로
복원할 수 없다.

- 생성은 Unicode 음절 산술만으로 가능하다.
- 복원은 사전 후보 생성과 문맥 순위화가 필요하다.
- 원문 의미 보존을 자동으로 가정하면 안 되고 사람 또는 별도 이해도 평가가 필요하다.
- clean 문장을 공격문으로 잘못 복원할 위험이 커 게이트웨이의 FPR 검사에 특히 중요하다.

#### O2. 종성 삽입·교체

종성이 없던 음절에 받침을 채우거나 기존 받침을 유사한 받침으로 바꾼다. 공개 변환기에서 흔히
"받침 넣기", "종성 채우기"로 제공된다. 인간은 중간 받침을 약하게 무시하며 읽을 수 있지만,
형태소 경계와 발음이 함께 바뀌므로 가역 변환이 아니다.

종성은 무작위 전체 집합보다 다음 두 조건으로 나눠야 한다.

1. `phonetic_final`: 종성 중화나 가까운 조음 위치를 반영한 후보
2. `crammed_final`: 의미 없는 받침을 삽입하는 시각·토큰 교란

두 조건을 합치면 음운 효과와 단순 노이즈 효과를 구분할 수 없다.

### 3.4 음운 표기 변형

#### P1. 초성 유사음 치환

초성을 평음·경음·격음 또는 IPA상 가까운 음으로 바꾼다. PHISH는 음절 안에서 치환 가능한 자모를
찾고 lookup table에서 유사음을 무작위 선택한다. KOTOX의 대표 규칙에는 `ㄱ→ㄲ/ㅋ`,
`ㄷ→ㄸ/ㅌ`, `ㅂ→ㅃ/ㅍ`, `ㅅ→ㅆ`, `ㅈ→ㅉ/ㅊ` 등이 포함된다.

현재 `experiment/disparity` 브랜치의 `tensify`는 모든 적용 가능한 초성 `ㄱ/ㄷ/ㅂ/ㅅ/ㅈ`을
문맥과 무관하게 경음으로 바꾼다. 따라서 정확한 이름은 **된소리되기**보다
`onset_lenis_to_tense`가 낫다. 실제 된소리되기는 앞뒤 음운·형태 조건이 있는 현상이다.

#### P2. 중성 유사음 치환·이중모음화

`ㅐ↔ㅔ`, 단모음→반모음 포함 이중모음처럼 가깝게 들리는 중성을 치환한다. 발음 유사도는 화자와
문맥에 따라 달라지므로 고정 표만으로 의미 보존을 보장할 수 없다. PHISH식 lookup, KOTOX 규칙,
실사용 변환기 표를 분리해 provenance를 남긴다.

#### P3. 연음·재음절화

앞 음절의 종성을 뒤 음절의 무음 초성 `ㅇ` 위치로 옮겨 발음대로 다시 조합한다. 예를 들어
`먹을게`를 `머글게`로 적는다. KOTOX는 forward liaison뿐 아니라 반대 방향으로 받침을 되넣는
reverse liaison도 별도 규칙으로 둔다.

현재 구현의 `liaison`은 다음 제한이 있다.

- 뒤 음절 초성이 `ㅇ`인 단순 인접 음절만 처리
- 겹받침과 종성 `ㅇ` 제외
- 형태소·어절 경계를 검사하지 않음

파일럿에는 이 제한을 manifest에 기록하고, 이후 표준 발음 기반 버전과 분리해야 한다.

#### P4. 구개음화 표기

받침 `ㄷ/ㅌ` 뒤에 조사·접미사의 `ㅣ`가 결합할 때 발음되는 `ㅈ/ㅊ`을 표기에 반영한다.
국립국어원의 표준 발음법 제17항은 `굳이→[구지]`, `밭이→[바치]`와 같은 조건을 설명한다
([국립국어원](https://www.korean.go.kr/front/onlineQna/onlineQnaView.do?mn_id=216&pageIndex=1&qna_seq=311921)).

현재 `palatalize`는 문자 패턴 `ㄷ/ㅌ + 이`만 보고 적용해 조사·접미사 여부를 판단하지 않는다.
이는 재현 가능한 합성 공격으로는 쓸 수 있지만 "표준 발음법 구현"으로 부르면 안 된다.

#### P5. 전체 발음 표기

G2P(grapheme-to-phoneme) 결과를 다시 한글 표면형으로 사용한다. 연음, 비음화, 유음화, 경음화,
격음화 등이 한 번에 섞일 수 있다. `g2pK`는 형태소 분석으로 문맥을 보고 문장을 발음대로 반환하며,
규범적·기술적 발음 옵션과 규칙별 verbose 출력을 제공한다
([g2pK](https://github.com/Kyubyong/g2pK)).

전체 G2P는 현실적인 복합 난독화 후보지만 단일 기법 효과를 귀속하기 어렵다. 따라서
`g2p_surface`는 composed/diagnostic 조건으로 두고, 개별 음운 규칙 결과와 섞지 않는다.

### 3.5 분절·순서 변형

#### S1. 띄어쓰기 교란

공백을 모두 제거하거나 음절·형태소 내부에 삽입한다. 원래 한국어 띄어쓰기 변이와 공격성 노이즈가
겹치므로 benign 구어체에서도 반드시 검사해야 한다.

강도는 "0.5 미만이면 삽입, 이상이면 전체 삭제"처럼 연산 종류를 바꾸지 말고 다음처럼 분리한다.

- `space_delete`: 기존 공백 중 삭제한 비율
- `space_insert`: 삽입 가능한 경계 중 삽입한 비율
- `space_mixed`: 두 연산의 합성, 단일 결과와 별도 보고

#### S2. 음절 재배열

단어 내부의 인접 음절을 교환하거나 가운데 음절만 섞는다. KOTOX는 음절 inventory와 편집 거리를
제한해 원문을 추론할 여지를 남긴다. 의미 손실 가능성이 높으므로 독립된 lossy family로 둔다.

### 3.6 시각·교차 문자권 변형

#### V1. 한글 닮은꼴·회전형

야민정음처럼 음절 블록 또는 자모의 모양을 다른 한글로 치환하거나 90°/180° 회전해 읽는다.
이 방법은 Unicode상 confusable이 아니라 공동체 관습에 의존하는 경우가 많다. UTS #39 skeleton만으로
한국어 밈 전체를 복원할 수 없으며 별도 사전이 필요하다.

#### V2. 교차 script 치환

한글 일부를 닮은 한자·가나·라틴 문자·기호·emoji로 바꾼다. KOTOX는 음절 블록과 자모 수준을 모두
사용한다. UTS #39의 `skeleton()`은 Unicode confusables 데이터에 등록된 시각 혼동 문자열을 비교하는
표준 메커니즘이지만, 모든 한국어 커뮤니티 닮은꼴을 포괄하는 번역기는 아니다.

`homoglyph`는 V2에 사용하고 U+200B 삽입에는 사용하지 않는다. 투명문자는 닮은 글자가 아니라
보이지 않는 format 문자다.

### 3.7 음차·번역·화용 변형

#### T1. 로마자·키보드 음차

한글 음절 일부를 라틴 발음 표기나 두벌식 영문 키 입력으로 바꾼다. `안녕→dkssud` 같은 키보드
전환은 결정론적으로 복원할 수 있지만, 자유 로마자 표기는 표준·사용자 습관에 따라 후보가 많다.

#### T2. 의미 번역·재음차

단어의 의미를 영어·일본어 등으로 번역하고 그 발음을 다시 한글 또는 혼합 script로 적는다.
KOTOX도 라틴 음차와 의미 치환은 단순 문자표보다 문맥 추론이 필요해 LLM 기반으로 생성했다.
이는 표기 정규화보다 번역·패러프레이즈 공격에 가까우므로 k-safeguard의 첫 구현에서 제외한다.

#### R1. 기호·emoji 삽입

감정 표현 주변에 괄호, 하트, emoji 등을 넣어 토큰 경계를 깨거나 표면 감성을 바꾼다. 단순 삭제로
복원 가능한 경우가 많지만, 정상 사용자도 흔히 쓰므로 공격 문자열만 보고 삭제하면 UX와 FPR을
악화시킬 수 있다.

## 4. 라이브러리와 공개 구현

### 4.1 Python

| 도구 | 확인 버전·라이선스 | 제공 기능 | 적합한 용도 | 주의점 |
|---|---|---|---|---|
| `unicodedata` | Python 표준 라이브러리 | NFC/NFKC/NFD/NFKD | U1·U4 baseline | 호환 자모 위치 추론, ZWSP 제거, 음운 복원은 못 함 |
| [`jamo`](https://github.com/JDongian/python-jamo) | PyPI 0.4.1, Apache-2.0 | 한글 음절·자모 분해와 합성, 넓은 Unicode 한글 범위 | 결합 자모 기반 변환 | README가 beta API임을 명시; 버전 고정 필요 |
| [`hgtk`](https://github.com/bluedisk/hangul-toolkit) | PyPI 0.2.1, Apache-2.0 | 글자/문장 자모 분해·조합, 한글 검사 | 호환 자모와 음절 조작 | 자체 조합 구분 문자를 사용하므로 저장 형식을 명시해야 함 |
| [`g2pK`](https://github.com/Kyubyong/g2pK) | PyPI 0.9.4, Apache-2.0 | 형태소 문맥 기반 발음 변환, 규칙 trace | P3~P5 생성·분석 | 2022년 이후 upstream push가 없고 MeCab·KoNLPy 등 의존성이 큼 |
| [`KoG2Padvanced`](https://github.com/seongmin-mun/KoG2Padvanced) | 배포 package·라이선스 표기 없음 | KoG2P에 추가 음운 규칙 적용 | 연구 비교 | 명시 라이선스가 없어 코드 복사·vendor 금지, 사용 전 허가 확인 |
| [`KOTOX`](https://github.com/leeyejin1231/KOTOX) | 코드·HF 데이터 MIT | 17개 난독화 규칙, 정렬 데이터, 생성 코드 | taxonomy·seed·규칙 참고 | pip 라이브러리가 아니며 일부 생성은 OpenAI·KoG2Padvanced 의존 |

버전과 저장소 상태는 2026-08-05에 PyPI·GitHub API로 확인했다. "최근 push"는 품질 보증이 아니며,
도입 전 최소 Python 버전, transitive dependency, 테스트와 라이선스를 다시 확인해야 한다.

### 4.2 JavaScript·TypeScript

| 도구 | 라이선스 | 제공 기능 | 적합한 용도 | 주의점 |
|---|---|---|---|---|
| [`Hangul.js`](https://github.com/e-/Hangul.js) | MIT | `disassemble`, `assemble`, 자모 기반 검색 | 브라우저 변환기·데모 | `assemble(disassemble(x))`가 항상 원문과 같지는 않음을 문서가 명시 |
| [`es-hangul`](https://github.com/toss/es-hangul) | MIT | 초성 추출 등 현대 ESM 한글 API | 새 웹 UI·초성체 | 음운 규칙 엔진은 아니므로 lookup/G2P는 별도 필요 |

브라우저 데모만 필요하면 JS 생태계가 편하지만, 평가 하네스와 모델 추론이 Python 중심이라면
생성기의 정본은 Python에 두고 웹 UI가 동일한 test vector를 공유하는 편이 재현성이 높다.

### 4.3 표준·보조 데이터

- [Unicode UAX #15](https://www.unicode.org/reports/tr15/): 정규화와 한글 canonical 분해·조합
- [Unicode UTS #39](https://www.unicode.org/reports/tr39/): confusable skeleton, mixed-script 탐지,
  identifier 보안 profile
- [국립국어원 한국어 어문 규범](https://www.korean.go.kr/kornorms/main/main.do): 연음·구개음화·경음화
  등 규칙의 기준
- [KOTOX dataset](https://huggingface.co/datasets/ssgyejin/KOTOX): 원문↔난독화문 정렬 pair와 rule label

## 5. 공개 웹 변환기 동작 조사

이 절은 2026-08-05에 공개 HTML·JavaScript와 무해한 입력의 응답을 확인한 결과다. 서비스 구현은
언제든 바뀔 수 있다. 소스가 공개 저장소로 배포된 것이 아니므로 알고리즘을 그대로 복사하지 않고
동작 원리와 실험 아이디어만 참고한다.

### 5.1 요약

| 서비스 | 처리 위치 | 확인한 핵심 연산 | 무작위성 | 연구 활용 판단 |
|---|---|---|---|---|
| [한글 난독화/airbnbfy](https://airbnbfy.hanmesoft.com/) | 브라우저 React bundle | 연음, 다음 초성의 받침 중복, 유사 자모 치환, 무의미 종성 추가 | 있음 | 기법·강도 UI 참고 |
| [ATOG 난독화기](https://atog.kr/nandoc) | 브라우저 Next.js bundle | Unicode 음절 분해 → 유사 초·중·종성 lookup → 재조합 | 있음, 3개 후보 | lookup 설계 참고 |
| [xeno 번역 방해기](https://xeno.work/koenc.html) | 브라우저 정적 JS | 음절 섞기, 받침 매핑, 발음 regex, random, 세로쓰기 | 일부 있음 | 연산 분리 방식 참고 |
| [인스타공백닷컴](https://www.instablank.com/hangulEnc) | 서버 AJAX POST | 레벨 1~4의 종성·유사음 중심 변형 | 있음 | 민감 입력 사용 금지, black-box 비교만 |
| [후니소프트 변환기](https://www.jhnsoft.co.kr/korean-converter/) | 브라우저 inline JS | 음절별 고정 regex 치환표를 순서대로 적용 | 없음 | deterministic baseline 참고 |

### 5.2 airbnbfy

공개 bundle build `main.0aa90e06.chunk.js`를 확인했다.

- 네 개의 0~100 slider가 연음, 뒤 초성의 받침 중복, 유사 자모 치환, 무의미 종성 추가 비율을
  각각 제어한다.
- 음절을 초·중·종성으로 나누고, 각 component의 유사 후보표에서 무작위 선택한 뒤 재조합한다.
- "완성형 글자만 허용" 옵션은 생성한 음절이 내부 whitelist에 있을 때만 채택하고 최대 10회
  재시도한다.
- 변환 함수는 브라우저 bundle 안에서 실행된다. Google Analytics가 별도로 포함되어 있으므로
  이를 개인정보 비수집 보장으로 확대 해석하지 않는다.

프로젝트에는 네 slider를 한 개의 `intensity`로 합치지 말고 각 operator별 적용 가능 위치와 실제
변경 비율을 따로 저장하는 설계를 참고할 수 있다.

### 5.3 ATOG

공개 Next.js chunk `app/nandoc/page-8afd799a7d27f3ea.js`를 확인했다.

- U+AC00~U+D7A3 음절을 `(초성, 중성, 종성)` index로 분해한다.
- 초성·중성·종성별 유사 후보 배열에서 `Math.random()`으로 하나를 고르고 음절을 재조합한다.
- "초성 변경하기"와 "종성 채우기" 옵션을 제공한다.
- 한 번 누르면 서로 다른 난독화 후보 3개를 만든다.
- 변환 계산은 클라이언트에서 수행되고 별도의 사용 횟수 기록 호출이 있다. 정적 소스상 변환
  함수가 원문을 서버로 전달하지는 않지만, 전체 사이트의 개인정보 처리를 보증하는 조사는 아니다.

이 구현은 단순하고 빠르지만 seed를 받을 수 없어 동일 입력의 재현성이 없다. benchmark 구현은
반드시 별도 PRNG와 `generation_seed`를 받도록 해야 한다.

### 5.4 xeno.work

공개 `/js/koenc.js?v=2023091105`를 확인했다.

- `섞기`: 4음절 이상 한글 run에서 양끝을 두고 내부 인접 음절을 쌍으로 교환한다.
- `받침넣기`: 각 종성 index를 고정 lookup의 다른 종성으로 매핑한다.
- `발음꼬기`: 호환 자모로 분해하고 regex 규칙을 순서대로 적용한 뒤 다시 조합한다.
- `랜덤`: 한글 run 길이에 따라 섞기·받침·발음 중 하나를 선택한다.
- `최적화`: 4음절 미만에는 받침, 그 이상에는 섞기를 적용한다.
- 세로쓰기는 비ASCII 문자를 여러 행으로 재배치한다.
- 변환은 브라우저 안에서 수행되지만 "번역 확인" 버튼은 결과를 각 번역 서비스 URL에 넣어 새
  창을 연다. 민감 문장을 누르면 제3자 번역 서비스로 전송될 수 있다.

### 5.5 인스타공백닷컴

페이지의 form action과 inline JavaScript를 확인했다. 원문과 `change_level`을
`/ajax/ajax_hangul_change_jiraksil.php`에 POST하고 서버가 변환문을 반환한다.

무해 입력 `안녕하세요 한국어 테스트입니다`를 레벨 1~4로 호출한 결과 종성 추가·교체와 유사한
음절 치환이 단계별로 늘어났다. 같은 레벨 2를 세 번 호출했을 때 결과가 모두 달라 확률적 생성임도
확인했다.

- 장점: 사람이 실제로 쓰는 변환기의 black-box 분포를 관찰할 수 있다.
- 단점: 내부 규칙·seed가 공개되지 않아 재현 benchmark의 정본으로 쓸 수 없다.
- 보안: 입력이 서버로 전송되므로 실제 공격 payload, 비밀, 개인정보를 넣지 않는다.
- 문서상 "난독화·캠브리지·싸이월드체"를 지원한다고 쓰여 있지만 현재 확인한 UI에는 레벨 1~4만
  노출됐다. 사이트 설명과 현재 동작을 구분해야 한다.

### 5.6 후니소프트

페이지 inline JavaScript에 음절별 `replace()` 호출이 긴 고정표로 들어 있다. 입력을 순서대로
치환하므로 결과는 결정론적이고 서버 변환 요청은 없다.

- 장점: 동일 입력에 동일 출력이 나오는 간단한 baseline이다.
- 단점: 규칙 출처·언어학적 근거·커버리지가 명시되지 않았고, 순차 replace는 앞선 출력이 뒤
  규칙에 다시 걸릴 가능성을 검토해야 한다.
- 활용: 구현을 복사하지 않고, 고정 음절 치환표라는 별도 공격군이 실사용에 존재한다는 근거로만
  사용한다.

### 5.7 웹 도구에서 얻은 공통 설계

공개 변환기들은 대체로 다음 파이프라인을 쓴다.

```text
입력
  → 완성형 한글 범위 확인
  → 초·중·종성 index 분해
  → lookup/regex/재배열 연산
  → 유효 음절 재조합
  → 복사 또는 외부 번역기 확인
```

차이는 변환 위치와 후보를 어떻게 고르는지다. 연구용 구현에서는 웹 도구보다 다음 정보가 더
필요하다.

- PRNG seed와 알고리즘 버전
- 적용 가능한 위치 수와 실제 변경 위치 수
- 선택된 원자 규칙 목록
- 원문과 같은 결과인지 `changed`
- 의미 손실 가능성 `lossy`
- 외부 전송 없이 로컬에서 실행되는지

## 6. 현재 `ko_obfuscator.py`와의 대응

`experiment/disparity` 브랜치의 구현을 위 taxonomy에 매핑하면 다음과 같다.

| 현재 함수 | 정확한 분류 | 유지할 점 | 수정·명시할 점 |
|---|---|---|---|
| `jamo_decompose` | U2 호환 자모 분해 | 간단하고 결정론적 | 이름에 `compat_jamo` 명시; NFKC 완전 복원 가정 금지 |
| `chosung` | O1 초성체 | lossy 대조군 | 의미 보존 자동 판정 금지 |
| `tensify` | P1 초성 평음→경음 치환 | 핵심 음운 후보 | 표준 된소리되기와 구분해 `onset_lenis_to_tense` 권장 |
| `break_spacing` | S1 공백 삽입/삭제 | tokenizer 교란 대조군 | 삽입과 삭제를 별도 technique으로 분리 |
| `zwsp_inject` | U3 투명문자 삽입 | Unicode 대조군 | 주석의 `호모글리프` 표현 제거 |
| `liaison` | P3 단순 forward liaison | 핵심 음운 후보 | 겹받침·형태소 경계 제외를 명시 |
| `palatalize` | P4 문자 패턴 구개음화 | 핵심 음운 후보 | 조사·접미사 문맥 미검사 명시 |

추가 우선순위는 다음과 같다.

1. `onset_lenis_to_aspirated`, `medial_near_sound`, `final_near_sound`
2. `final_insertion`과 `space_insert`/`space_delete` 분리
3. canonical Jamo U1과 compatibility Jamo U2를 별도 구현
4. PHISH식 single/dual-jamo attack과 `applicable_syllable_ratio` 강도
5. `g2p_surface` composed 진단 조건
6. KOTOX의 look-alike·cross-script·anagram은 주력 음운 결과 확인 후 추가

## 7. 생성기 구현 권고

### 7.1 공통 인터페이스

```text
transform(
  text,
  technique,
  intensity,
  generation_seed,
  preserve_valid_syllable=true
) -> {
  text_variant,
  changed,
  applicable_positions,
  changed_positions,
  operations,
  lossy,
  warnings
}
```

`intensity`는 문자열 길이가 아니라 **적용 가능한 위치 중 변경한 위치 비율**로 정의한다.
PHISH도 먼저 치환 가능한 음절을 찾은 뒤 그 집합을 기준으로 공격 비율을 계산한다.

### 7.2 결정론과 후보표

- Python 전역 `random`을 공유하지 말고 변환 호출별 PRNG를 만든다.
- 후보 배열, regex와 G2P version을 manifest에 기록한다.
- 원문 자기 자신을 후보에 넣었다면 실제 변경 수를 따로 센다.
- 동일 seed·version·입력은 byte-for-byte 같은 결과를 내야 한다.
- Unicode version과 normalization form도 고정한다.

### 7.3 의미 보존

기법별로 의미 보존 검사를 다르게 한다.

| 기법 | 최소 검사 |
|---|---|
| U1/U3/U4 | 정규화·제거 후 exact restoration |
| U2 | 한글 오토마타 복원 + exact/후보 수 |
| P1~P5 | 발음 유사도 + 사람 또는 intent recognition |
| O1/S2/T2 | 사람 검수 필수, 자동 통과 금지 |
| V1/V2 | glyph 사전 provenance + 사람 가독성 |
| R1 | 기호 제거 후 exact restoration + benign FPR |

### 7.4 합성 공격

KOTOX는 easy/normal/hard에 2/3/4개 규칙을 조합하지만, k-safeguard는 먼저 single-technique 효과를
확인해야 한다. 조합은 다음 순서로 별도 실험한다.

1. normalization-recoverable끼리 조합
2. phonological끼리 조합
3. phonological + visual/segmentation 교차 조합

연산 순서가 결과를 바꾸므로 `operations`에 적용 순서를 저장한다. 같은 네 규칙이라도 순서가 다르면
별도 variant다.

## 8. 추천 실험 범위

### 8.1 첫 파일럿에 포함

- 주력 phonetic: `onset_lenis_to_tense`, `liaison`, `palatalize`
- 확장 phonetic: `onset_lenis_to_aspirated`, `medial_near_sound`, `final_near_sound`
- Unicode 대조군: canonical jamo, compatibility jamo, ZWSP
- 구조 대조군: chosung, space insertion, space deletion

각 기법은 single-technique, intensity 0.5/1.0, 생성 seed 17/42/2026으로 맞춘다. 결정론적 변환은
중복 출력을 만들지 않는다.

### 8.2 첫 파일럿에서 제외

- 의미 번역·재음차
- LLM이 자유 생성한 난독화
- 회전형 야민정음 전체 사전
- 음절 anagram과 세로쓰기
- 2개 이상 기법의 조합

이들은 유효한 실사용 난독화지만 원자 기법 귀속과 의미 보존 검수가 어려워 초기 go/no-go의 분산을
키운다.

## 9. 주의 사항

- 공개 웹 변환기의 "번역기가 못 읽는다"는 설명은 성능 근거가 아니다. 동일한 평가셋과 metric으로
  직접 측정하기 전에는 인용문 이상의 의미를 부여하지 않는다.
- PHISH의 대상은 한국어 혐오 표현 분류기이고 KOTOX의 대상은 유해 텍스트 분류·복원이다. 이 결과를
  LLM 가드레일 회피율로 그대로 일반화하지 않는다.
- 음운 변형의 역함수는 대부분 many-to-one이다. 게이트웨이는 복호화기가 아니라 best-effort
  후보 생성기다.
- 정상 통신체·사투리·오타·이모지를 공격으로 단정하지 않는다. 정규화 결과와 원문을 함께 보존하고
  최종 판단은 하위 가드레일에 맡긴다.
- 외부 웹 변환기에 미공개 공격문, system prompt, 개인정보나 비밀을 입력하지 않는다.
- `homoglyph`, `jamo decomposition`, `zero-width`, `phonetic substitution`을 한 단어 "문자 난독화"로
  뭉뚱그리지 않는다.

## 10. 출처

### 연구

- Cho, W. I. & Kim, S. (2021),
  [Google-trickers, Yaminjeongeum, and Leetspeak](https://aclanthology.org/2021.wnut-1.7/)
- Kim, B. et al. (2025),
  [PHISH in MESH](https://arxiv.org/abs/2505.21380)
- Lee, Y. et al. (2025),
  [KOTOX: A Korean Toxic Dataset for Deobfuscation and Detoxification](https://arxiv.org/abs/2510.10961)

### 표준·공식 규범

- Unicode Consortium, [UAX #15: Unicode Normalization Forms](https://www.unicode.org/reports/tr15/)
- Unicode Consortium, [UTS #39: Unicode Security Mechanisms](https://www.unicode.org/reports/tr39/)
- 국립국어원, [한국어 어문 규범](https://www.korean.go.kr/kornorms/main/main.do)

### 구현·데이터

- [KOTOX GitHub](https://github.com/leeyejin1231/KOTOX) ·
  [KOTOX Hugging Face](https://huggingface.co/datasets/ssgyejin/KOTOX)
- [g2pK](https://github.com/Kyubyong/g2pK) ·
  [KoG2Padvanced](https://github.com/seongmin-mun/KoG2Padvanced)
- [python-jamo](https://github.com/JDongian/python-jamo) ·
  [hgtk](https://github.com/bluedisk/hangul-toolkit)
- [Hangul.js](https://github.com/e-/Hangul.js) ·
  [es-hangul](https://github.com/toss/es-hangul)
- [airbnbfy](https://airbnbfy.hanmesoft.com/) ·
  [ATOG](https://atog.kr/nandoc) ·
  [xeno.work](https://xeno.work/koenc.html) ·
  [인스타공백닷컴](https://www.instablank.com/hangulEnc) ·
  [후니소프트](https://www.jhnsoft.co.kr/korean-converter/)
