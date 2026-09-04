#!/usr/bin/env python3
"""
FlavorWheel Reference Index Auto-Updater
docs/references 폴더 내의 파일(논문 PDF, 마크다운 요약, 기술 문서 등)을 스캔하여
docs/references/README.md의 참고 자료 인덱스 테이블을 자동으로 분석 및 업데이트합니다.

사용법:
  단발성 실행: python3 scripts/update_references.py
  실시간 감시: python3 scripts/update_references.py --watch
"""

import os
import re
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
REFERENCES_DIR = BASE_DIR / "docs" / "references"
README_PATH = REFERENCES_DIR / "README.md"

IGNORED_FILES = {"README.md", ".DS_Store", "update_references.py"}
IGNORED_EXTENSIONS = {".py", ".sh", ".tmp", ".swp"}

CATEGORY_KEYWORDS = {
    "감각 과학": [
        "whisky", "whiskey", "flavor", "flavour", "aroma", "sensory", "taste",
        "smell", "wine", "coffee", "beer", "tea", "wheel", "swa", "sca", "scent",
        "olfactory", "gustatory", "미각", "후각", "향미", "위스키", "플레이버"
    ],
    "데이터 캘리브레이션": [
        "calibration", "bradley", "terry", "pairwise", "z-score", "ranking",
        "vector", "cosine", "embedding", "recommendation", "ml", "ai", "similarity",
        "bias", "normalization", "elo", "정규화", "캘리브레이션", "추천", "유사도"
    ],
    "프론트엔드": [
        "flutter", "custompainter", "canvas", "radar", "chart", "sunburst", "pie",
        "rendering", "ui", "ux", "visualization", "widget", "graphic", "시각화", "렌더링"
    ],
    "분산 아키텍처": [
        "offline", "sync", "local-first", "isar", "drift", "crdt", "etag", "cache",
        "rest", "grpc", "database", "distributed", "broker", "동기화", "오프라인", "분산"
    ],
}

def clean_filename_title(filename: str) -> str:
    stem = Path(filename).stem
    # Replace separators with spaces
    cleaned = re.sub(r"[_\-\.]+", " ", stem)
    # Title-case each word if all lowercase
    if cleaned.islower():
        cleaned = cleaned.title()
    return cleaned.strip()

def extract_pdf_info(filepath: Path) -> dict:
    info = {"title": "", "author": "", "summary": ""}
    try:
        with open(filepath, "rb") as f:
            content = f.read(65536)  # Read first 64KB for metadata
            # Try to find /Title (xxx) or /Title <hex>
            title_match = re.search(rb"/Title\s*\((.*?)\)", content)
            if title_match:
                try:
                    title_bytes = title_match.group(1)
                    if title_bytes.startswith(b"\xfe\xff"):
                        info["title"] = title_bytes[2:].decode("utf-16-be", errors="ignore")
                    else:
                        info["title"] = title_bytes.decode("utf-8", errors="ignore")
                except Exception:
                    pass

            author_match = re.search(rb"/Author\s*\((.*?)\)", content)
            if author_match:
                try:
                    author_bytes = author_match.group(1)
                    if author_bytes.startswith(b"\xfe\xff"):
                        info["author"] = author_bytes[2:].decode("utf-16-be", errors="ignore")
                    else:
                        info["author"] = author_bytes.decode("utf-8", errors="ignore")
                except Exception:
                    pass
    except Exception as e:
        print(f"[Warning] Failed to read PDF metadata for {filepath.name}: {e}")

    if not info["title"]:
        info["title"] = clean_filename_title(filepath.name)
    if not info["author"]:
        info["author"] = "학술/연구 자료"
    return info

def extract_md_info(filepath: Path) -> dict:
    info = {"title": "", "author": "", "summary": "", "category": ""}
    try:
        text = filepath.read_text(encoding="utf-8")
        lines = text.splitlines()

        # Check for YAML frontmatter
        if text.startswith("---"):
            fm_match = re.search(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
            if fm_match:
                fm = fm_match.group(1)
                for line in fm.splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        k = k.strip().lower()
                        v = v.strip().strip('"\'')
                        if k == "title":
                            info["title"] = v
                        elif k in ("author", "authors"):
                            info["author"] = v
                        elif k in ("summary", "description"):
                            info["summary"] = v
                        elif k in ("category", "topic"):
                            info["category"] = v

        # Fallback to heading
        if not info["title"]:
            for line in lines:
                if line.startswith("# "):
                    info["title"] = line[2:].strip()
                    break

        # Fallback summary
        if not info["summary"]:
            for line in lines:
                if line.startswith("> "):
                    info["summary"] = line[2:].strip()
                    break
    except Exception as e:
        print(f"[Warning] Failed to parse markdown {filepath.name}: {e}")

    if not info["title"]:
        info["title"] = clean_filename_title(filepath.name)
    if not info["author"]:
        info["author"] = "내부 기술 문서"
    return info

def extract_generic_info(filepath: Path) -> dict:
    return {
        "title": clean_filename_title(filepath.name),
        "author": "기술 자료",
        "summary": f"{filepath.suffix.upper()} 참조 파일"
    }

def categorize(title: str, summary: str, filename: str, explicit_cat: str = "") -> str:
    if explicit_cat:
        for cat in CATEGORY_KEYWORDS:
            if explicit_cat.lower() in cat.lower():
                return cat

    combined = f"{title} {summary} {filename}".lower()
    for cat, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in combined:
                return cat
    return "기타 기술 자료"

def scan_references() -> list:
    items = []
    if not REFERENCES_DIR.exists():
        return items

    files = sorted(REFERENCES_DIR.iterdir(), key=lambda p: p.name.lower())
    for f in files:
        if f.is_dir() or f.name in IGNORED_FILES or f.name.startswith("."):
            continue
        if f.suffix.lower() in IGNORED_EXTENSIONS:
            continue

        ext = f.suffix.lower()
        if ext == ".pdf":
            data = extract_pdf_info(f)
        elif ext in (".md", ".markdown"):
            data = extract_md_info(f)
        else:
            data = extract_generic_info(f)

        category = data.get("category") or categorize(data["title"], data.get("summary", ""), f.name)
        
        # Calculate file size display
        size_bytes = f.stat().st_size
        if size_bytes < 1024:
            size_str = f"{size_bytes}B"
        elif size_bytes < 1024 * 1024:
            size_str = f"{size_bytes / 1024:.1f}KB"
        else:
            size_str = f"{size_bytes / (1024*1024):.1f}MB"

        items.append({
            "filename": f.name,
            "title": data["title"],
            "author": data["author"],
            "summary": data.get("summary", "") or f"{category} 관련 참조 자료",
            "category": category,
            "ext": ext,
            "size": size_str
        })
    return items

def generate_index_markdown(items: list) -> str:
    if not items:
        return "*현재 등록된 참조 자료가 없습니다. `docs/references/` 폴더에 PDF나 마크다운 파일을 추가하면 자동으로 색인됩니다.*\n"

    lines = [
        "| ID | 카테고리 | 문서/논문 제목 | 저자 / 출처 | 관련 설계 영역 및 요약 | 파일 (크기) |",
        "| :---: | :---: | :--- | :--- | :--- | :--- |"
    ]
    for idx, item in enumerate(items, 1):
        ref_id = f"**REF-{idx:02d}**"
        title_link = f"[{item['title']}](file://{REFERENCES_DIR / item['filename']})"
        lines.append(
            f"| {ref_id} | {item['category']} | {title_link} | {item['author']} | {item['summary']} | `{item['filename']}` ({item['size']}) |"
        )
    return "\n".join(lines) + "\n"

def update_readme():
    if not README_PATH.exists():
        print(f"[Error] {README_PATH} not found.")
        return

    items = scan_references()
    table_md = generate_index_markdown(items)

    content = README_PATH.read_text(encoding="utf-8")
    header_pattern = r"(## 📋 참고 자료 인덱스 \(Reference Index\)\s*\n\s*\*.*?\*\s*\n\n)([\s\S]*?)(\n---|\Z)"
    
    # Check if section exists
    if re.search(header_pattern, content):
        new_content = re.sub(
            header_pattern,
            rf"\1{table_md}\3",
            content
        )
    else:
        # Append section if missing
        new_content = content + f"\n\n## 📋 참고 자료 인덱스 (Reference Index)\n\n{table_md}\n"

    if new_content != content:
        README_PATH.write_text(new_content, encoding="utf-8")
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ✅ README.md 참고 자료 인덱스가 업데이트되었습니다. (총 {len(items)}개 파일)")
    else:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ℹ️ 변경사항이 없습니다. (총 {len(items)}개 파일 유지)")

def watch_directory(poll_interval: float = 2.0):
    print(f"👀 [Watcher] {REFERENCES_DIR} 폴더를 실시간 감시 중입니다... (종료: Ctrl+C)")
    last_mtimes = {}
    while True:
        try:
            current_mtimes = {}
            if REFERENCES_DIR.exists():
                for p in REFERENCES_DIR.iterdir():
                    if p.name in IGNORED_FILES or p.name.startswith("."):
                        continue
                    current_mtimes[p.name] = p.stat().st_mtime

            if current_mtimes != last_mtimes:
                last_mtimes = current_mtimes
                update_readme()
            time.sleep(poll_interval)
        except KeyboardInterrupt:
            print("\n👋 감시를 종료합니다.")
            break
        except Exception as e:
            print(f"[Error in watcher] {e}")
            time.sleep(poll_interval)

if __name__ == "__main__":
    if "--watch" in sys.argv:
        watch_directory()
    else:
        update_readme()
