# k-safeguard 정규화기 가중치 라이선스

이 Release의 `normalizer.onnx`, `tokenizer.json`, `char_vocab.json`은 CC BY-SA 4.0으로 배포합니다.
<https://creativecommons.org/licenses/by-sa/4.0/>

k-safeguard 코드는 이 라이선스가 아니라 Apache-2.0입니다.

## 학습 데이터

아래 문장을 난독화해 학습에 사용했습니다.

- 한국어 위키백과, 위키백과 기여자, CC BY-SA 4.0 (`wikimedia/wikipedia`, `20231101.ko`)
- KLUE, `klue/klue`의 `ynat`·`nli`, CC BY-SA 4.0

## 기반 모델

- KcELECTRA-base-v2022, Junbum Lee, MIT (`beomi/KcELECTRA-base-v2022`, revision `87285578b4686b6d190abd40e947a2a416add6de`)

## 변경 사항

KcELECTRA에 글자 편집 태거를 얹어 전체 미세조정하고 ONNX로 변환했습니다. 토크나이저는 KcELECTRA의 것을
`tokenizer.json`으로 내보냈고, `char_vocab.json`은 학습 데이터의 글자 목록입니다.

## 재배포

가중치를 고치거나 파인튜닝해 배포할 때는 같은 라이선스로 내고 위 출처를 함께 밝혀 주세요.

## KcELECTRA 고지

MIT License

Copyright (c) 2021 Junbum Lee

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
