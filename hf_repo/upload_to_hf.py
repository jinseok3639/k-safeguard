"""
upload_to_hf.py — 이 폴더를 허깅페이스 데이터셋 리포로 업로드.

준비:  pip install huggingface_hub
       hf auth login            # 또는  export HF_TOKEN=hf_xxx
실행:  HF_REPO=your-username/ko-hangul-guardrail-bench python3 upload_to_hf.py

동일 명령을 CLI 한 줄로도 가능:
  hf upload your-username/ko-hangul-guardrail-bench . . --repo-type dataset
"""
import os
from huggingface_hub import HfApi

REPO_ID = os.environ.get("HF_REPO", "your-username/ko-hangul-guardrail-bench")
HERE = os.path.dirname(os.path.abspath(__file__))

api = HfApi()
api.create_repo(REPO_ID, repo_type="dataset", exist_ok=True, private=True)  # 먼저 비공개로
api.upload_folder(
    folder_path=HERE,
    repo_id=REPO_ID,
    repo_type="dataset",
    commit_message="Add Korean hangul-obfuscation guardrail robustness benchmark",
    ignore_patterns=["upload_to_hf.py", "__pycache__/*", "*.pyc"],
)
print(f"업로드 완료 → https://huggingface.co/datasets/{REPO_ID}")
print("Dataset Viewer가 뜨는지 확인하고, 문제없으면 웹 UI에서 Public으로 전환.")
