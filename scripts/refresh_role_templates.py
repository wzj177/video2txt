#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
覆盖角色模板提示词：使用 config/template_skills/<category>/SKILL.md
同步更新 template_skills + role_templates。
"""
import argparse
import json
import re
import sqlite3
from pathlib import Path

CODE_FENCE_PATTERN = re.compile(r"^```[\w-]*\n(?P<body>.*?)\n```$", re.DOTALL)


def split_frontmatter(md: str):
    lines = md.splitlines()
    if not lines or lines[0].strip() != "---":
        return "", md
    end_idx = None
    for idx, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_idx = idx
            break
    if end_idx is None:
        return "", md
    front = "\n".join(lines[1:end_idx])
    body = "\n".join(lines[end_idx + 1 :])
    return front, body


def parse_sections(body: str):
    sections = {}
    current = None
    buf = []
    for line in body.splitlines():
        if line.startswith("## "):
            if current:
                sections[current] = "\n".join(buf).strip()
            current = line[3:].strip()
            buf = []
        else:
            buf.append(line)
    if current:
        sections[current] = "\n".join(buf).strip()
    return sections


def strip_code_block(text: str) -> str:
    text = text.strip()
    match = CODE_FENCE_PATTERN.match(text)
    if match:
        return match.group("body").strip()
    return text


def build_prompt_schema(md: str):
    _, body = split_frontmatter(md)
    sections = parse_sections(body)
    prompt_schema = {}
    for key, value in sections.items():
        if re.search(r"prompt", key, re.I):
            norm_key = key.strip().lower().replace(" ", "_")
            prompt_schema[norm_key] = strip_code_block(value)
    return prompt_schema


def main():
    parser = argparse.ArgumentParser(description="覆盖角色模板提示词")
    parser.add_argument("--category", default="mind_map", help="模板类别 (default: mind_map)")
    parser.add_argument("--db", default="data/app.db", help="SQLite 数据库路径")
    parser.add_argument("--skill-dir", default="config/template_skills", help="模板目录")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        raise SystemExit(f"数据库不存在: {db_path}")

    skill_path = Path(args.skill_dir) / args.category / "SKILL.md"
    if not skill_path.exists():
        raise SystemExit(f"模板文件不存在: {skill_path}")

    markdown = skill_path.read_text(encoding="utf-8")
    prompt_schema = build_prompt_schema(markdown)
    if not prompt_schema:
        raise SystemExit("未解析到 prompt 段落，模板不合法")

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    cur.execute(
        "UPDATE template_skills SET prompt_schema = ?, skill_markdown = ? WHERE skill_key = ?",
        (json.dumps(prompt_schema, ensure_ascii=False), markdown, args.category),
    )
    skill_updated = cur.rowcount

    cur.execute(
        "UPDATE role_templates SET prompt_schema = ?, skill_markdown = ? WHERE category = ?",
        (json.dumps(prompt_schema, ensure_ascii=False), markdown, args.category),
    )
    role_updated = cur.rowcount

    conn.commit()
    conn.close()

    print(f"已更新 template_skills: {skill_updated} 条")
    print(f"已更新 role_templates: {role_updated} 条")


if __name__ == "__main__":
    main()
