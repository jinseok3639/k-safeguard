# k-safeguard 릴리스 절차

이 문서는 패키지 산출물을 검증하고 TestPyPI와 정식 PyPI에 배포하는 절차를 정의한다. 두 배포 모두 의도하지
않은 공개를 막기 위해 **수동 실행형 workflow_dispatch**로만 제공하며, 확인 문구 입력과 environment 승인
두 단계를 거친다. TestPyPI 검증(1~4절)을 통과한 버전만 정식 PyPI(6절)로 승격한다.

## 1. 버전 준비

릴리스 버전은 다음 두 파일에서 같아야 한다.

- `pyproject.toml`의 `[project].version`
- `src/k_safeguard/__init__.py`의 `__version__`

다음 명령은 두 값을 비교한다.

```bash
python tools/release/verify_artifacts.py --source-only
```

동일한 버전의 배포 파일은 PyPI와 TestPyPI에 다시 업로드할 수 없다. 재검증 배포가 필요하면 버전을 먼저
올리고 변경 이력을 확인한다.

## 2. 로컬 산출물 검증

```bash
python -m pip install --upgrade build twine
python -m build
python tools/release/verify_artifacts.py
python -m twine check dist/*
```

검증기는 다음 배포 경계를 확인한다.

- wheel 1개와 sdist 1개 및 소스와 메타데이터의 버전 일치
- OS 비종속 pure Python wheel tag인 `py3-none-any`
- 기본 설치의 외부 런타임 의존성 0개
- 패키지 코드와 `py.typed`, 라이선스·README 포함
- 실험 코드, 테스트, 데이터셋, 노트북과 모델 가중치의 wheel 제외

## 3. TestPyPI Trusted Publisher 최초 설정

장기 API 토큰은 저장소 secret으로 만들지 않는다. TestPyPI에 프로젝트가 아직 없다면 계정의
**Publishing** 화면에서 pending publisher를 만들고 프로젝트 이름 `k-safeguard`도 입력한다. 기존
프로젝트가 있다면 해당 프로젝트의 Publishing 설정을 사용한다. pending publisher는 첫 업로드 때
프로젝트를 만들고 일반 publisher로 전환되며, 등록만으로 패키지 이름을 선점하지는 않는다.

GitHub Trusted Publisher에는 다음 값을 입력한다.

| 항목 | 값 |
|---|---|
| PyPI project name | `k-safeguard` (pending publisher인 경우) |
| GitHub owner | `jinseok3639` |
| Repository | `k-safeguard` |
| Workflow | `testpypi.yml` |
| Environment | `testpypi` |

GitHub 저장소에도 `testpypi` environment를 만들고 팀 유지관리자를 required reviewer로 지정한다. 이
environment 승인은 확인 문구와 별개인 최종 업로드 승인선이다. Trusted Publisher의 repository,
workflow와 environment 값은 대소문자까지 실제 설정과 일치해야 한다.

## 4. 수동 배포와 원격 설치 확인

1. 배포 변경을 기본 브랜치에 병합한다.
2. GitHub Actions의 **Publish package to TestPyPI**를 연다.
3. 기본 브랜치를 선택하고 확인란에 `publish-testpypi`를 입력한다.
4. build job의 산출물·메타데이터 검증 결과를 확인한다.
5. `testpypi` environment 배포 요청을 승인한다.
6. smoke-test가 Python 3.10 환경에서 원격 wheel을 `--no-deps`로 설치하는지 확인한다.

워크플로는 TestPyPI 인덱스 반영 지연을 고려해 설치를 최대 5회 재시도한다. 로컬에서 같은 설치를 확인할
때는 다음 명령을 사용한다.

```bash
python -m pip install --no-deps \
  --index-url https://test.pypi.org/simple/ \
  "k-safeguard==0.1.0"
python -c "from k_safeguard import Gateway; assert Gateway().process('ㅇㅏㄴ').normalized == '안'"
```

## 5. 정식 PyPI 승격 전 체크

- PR의 Windows/Linux/macOS 및 지원 Python 테스트가 모두 성공했는가
- TestPyPI wheel 설치와 최소 API smoke test가 성공했는가
- 정상 입력 과잉 변경 및 공격 입력 복원 평가 결과가 현재 버전과 연결되는가
- 공개 API, 선택 dependency와 제한 사항이 README·PACKAGING 문서와 일치하는가
- 태그와 릴리스 노트에 패키지 버전 및 평가 근거를 기록했는가

## 6. 정식 PyPI 배포

정식 PyPI 업로드는 **되돌릴 수 없다.** 파일을 삭제해도 같은 버전 번호는 영구히 재사용할 수 없으므로, 5절
체크를 모두 통과한 뒤에만 실행한다.

### 6.1 Trusted Publisher 최초 설정

TestPyPI와 PyPI는 별개 서비스다. 계정, 프로젝트 등록과 Trusted Publisher를 각각 따로 만들어야 한다.
`https://pypi.org/manage/account/publishing/`에서 pending publisher를 만들고 다음 값을 입력한다.

| 항목 | 값 |
|---|---|
| PyPI project name | `k-safeguard` (pending publisher인 경우) |
| GitHub owner | `jinseok3639` |
| Repository | `k-safeguard` |
| Workflow | `pypi.yml` |
| Environment | `pypi` |

GitHub 저장소에도 `pypi` environment를 만들고 팀 유지관리자를 required reviewer로 지정한다. Trusted
Publisher에 입력한 workflow·environment 값과 실제 설정이 대소문자까지 일치해야 OIDC 인증이 통과한다.

### 6.2 배포 실행

1. 배포 대상 버전을 기본 브랜치에 병합한다.
2. GitHub Actions의 **Publish package to PyPI**를 연다.
3. 기본 브랜치를 선택하고 확인란에 `publish-pypi`를 입력한다.
4. build job의 산출물·메타데이터 검증 결과를 확인한다.
5. `pypi` environment 배포 요청을 승인한다.
6. smoke-test가 Python 3.10에서 공개 인덱스로부터 패키지를 설치하는지 확인한다.

TestPyPI workflow와 달리 smoke-test는 `--no-deps`와 `--index-url` 없이 설치한다. 실제 사용자와 동일한
경로로 의존성 해석까지 통과하는지 확인하기 위해서다.

### 6.3 배포 후

```bash
python -m pip install "k-safeguard==0.1.0"
python -c "from k_safeguard import Gateway; assert Gateway().process('ㅇㅏㄴ').normalized == '안'"
```

배포한 버전에 마일스톤 태그를 남기고 릴리스 노트에 평가 근거를 기록한다.

## 공식 참고 문서

- [PyPI Trusted Publishing 개요](https://docs.pypi.org/trusted-publishers/)
- [pending publisher로 새 프로젝트 만들기](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)
- [GitHub Actions에서 Trusted Publisher 사용하기](https://docs.pypi.org/trusted-publishers/using-a-publisher/)
- [Trusted Publishing 보안 고려사항](https://docs.pypi.org/trusted-publishers/security-model/)
