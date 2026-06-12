#!/usr/bin/env python3
"""
db-dict HTML Generator
从 Markdown 数据字典文件 + Java 实体类生成交互式 HTML 总览页。

用法:
    python generate_html.py --input-dir <tables_dir> --output <output_html> --database <db_name> \
        [--db-total-tables N] [--slice-tables N] [--entities-dir <domain_dir>] [--api-base <url>]
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
TEMPLATE_PATH = SCRIPT_DIR / "template.html"


def parse_md_table(lines, header_separator="|---"):
    """解析 Markdown 表格，返回列表 of dict"""
    result = []
    header = None
    for line in lines:
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if header is None:
            header = cells
            continue
        if all(c.replace("-", "").replace(":", "") == "" for c in cells):
            continue
        if len(cells) == len(header):
            row = dict(zip(header, cells))
            result.append(row)
    return result


def parse_table_md(filepath):
    """解析单个表的 Markdown 文件，返回结构化数据"""
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    lines = content.split("\n")
    data = {
        "table_name": "",
        "table_comment": "",
        "database": "",
        "column_count": 0,
        "index_count": 0,
        "row_count": "",
        "columns": [],
        "indexes": [],
        "foreign_keys": [],
        "analysis_records": [],
    }

    for line in lines:
        if line.startswith("# ") and not line.startswith("## "):
            data["table_name"] = line[2:].strip()
            break

    for line in lines:
        if line.startswith("> "):
            desc = line[2:].strip()
            parts = [p.strip() for p in desc.split("|")]
            if parts:
                data["table_comment"] = parts[0]
            for part in parts:
                if "数据库:" in part:
                    data["database"] = part.split(":", 1)[1].strip()
                elif "字段数:" in part:
                    try:
                        data["column_count"] = int(re.search(r"\d+", part).group())
                    except (AttributeError, ValueError):
                        pass
                elif "索引数:" in part:
                    try:
                        data["index_count"] = int(re.search(r"\d+", part).group())
                    except (AttributeError, ValueError):
                        pass
                elif "预估行数:" in part or "行数:" in part:
                    data["row_count"] = re.sub(r"[^\d,~]", "", part.split(":", 1)[-1]).strip()
            break

    current_section = None
    section_lines = []

    def flush_section():
        nonlocal current_section, section_lines
        if current_section and section_lines:
            rows = parse_md_table(section_lines)
            if current_section == "columns":
                data["columns"] = rows
            elif current_section == "indexes":
                data["indexes"] = rows
            elif current_section == "foreign_keys":
                data["foreign_keys"] = rows
            elif current_section == "analysis":
                data["analysis_records"] = rows
        section_lines = []

    for line in lines:
        if line.startswith("## 字段列表"):
            flush_section()
            current_section = "columns"
            continue
        elif line.startswith("## 索引"):
            flush_section()
            current_section = "indexes"
            continue
        elif line.startswith("## 外键关系"):
            flush_section()
            current_section = "foreign_keys"
            continue
        elif line.startswith("## 字段分析记录"):
            flush_section()
            current_section = "analysis"
            continue
        elif line.startswith("## "):
            flush_section()
            current_section = None
            continue

        if current_section:
            section_lines.append(line)

    flush_section()
    return data


def collect_all_tables(input_dir):
    """收集所有 Markdown 表文件"""
    tables = []
    input_path = Path(input_dir)
    if not input_path.exists():
        print(f"Error: Input directory not found: {input_dir}", file=sys.stderr)
        sys.exit(1)

    for md_file in sorted(input_path.glob("*.md")):
        if md_file.name == "summary.md":
            continue
        try:
            table_data = parse_table_md(md_file)
            if table_data["table_name"]:
                tables.append(table_data)
        except Exception as e:
            print(f"Warning: Failed to parse {md_file}: {e}", file=sys.stderr)

    return tables


# --- Java Entity Parsing ---

_CAMEL_RE = re.compile(r"(?<=[a-z])(?=[A-Z])")
_FIELD_RE = re.compile(r"^\s*private\s+(\S+)\s+(\w+)\s*;")
_CLASS_RE = re.compile(r"^\s*public\s+class\s+(\w+)")
_TABLENAME_RE = re.compile(r'@TableName\s*\(\s*["\']([^"\']+)["\']\s*\)')
_TABLEFIELD_RE = re.compile(r'@TableField\s*\(\s*(?:value\s*=\s*)?["\']([^"\']+)["\']')
_JAVADOC_RE = re.compile(r"/\*\*\s*(.*?)\s*\*/", re.DOTALL)
_EXIST_FALSE_RE = re.compile(r"@TableField\s*\(\s*exist\s*=\s*false\s*\)")


def _camel_to_prefix(name):
    """驼峰类名转小写前缀: OrderInfo -> order, StockBatch -> stock"""
    # 去掉常见后缀
    for suffix in ("Info", "WithBLOBs", "Opt", "Vo", "Order", "Payment", "Record", "Utils"):
        if name.endswith(suffix) and len(name) > len(suffix):
            name = name[: -len(suffix)]
            break
    # 取首段驼峰
    parts = _CAMEL_RE.split(name)
    return parts[0].lower() if parts else name.lower()


def _extract_javadoc_above(lines, field_idx):
    """从字段上方提取 Javadoc 注释"""
    # 往上找 /** 开头
    for i in range(field_idx - 1, max(field_idx - 6, -1), -1):
        line = lines[i].strip()
        if line.endswith("*/"):
            # 找到注释结束，继续往上找开始
            for j in range(i, max(i - 10, -1), -1):
                if "/**" in lines[j]:
                    block = "\n".join(lines[j : i + 1])
                    m = _JAVADOC_RE.search(block)
                    if m:
                        text = m.group(1)
                        # 清理: 去掉 * 前缀、@param 等
                        clean_lines = []
                        for cl in text.split("\n"):
                            cl = cl.strip().lstrip("* ").strip()
                            if cl and not cl.startswith("@"):
                                clean_lines.append(cl)
                        return " ".join(clean_lines).strip()
                    break
            break
        elif line == "" or line.startswith("//"):
            continue
        elif not line.startswith("*"):
            break
    return ""


def _extract_inline_comment(line):
    """提取行尾 // 注释"""
    idx = line.find("//")
    if idx > 0:
        return line[idx + 2 :].strip()
    return ""


def parse_java_entity(filepath):
    """解析单个 Java 实体类文件"""
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    lines = content.split("\n")
    class_name = ""
    table_name = ""
    fields = []
    skip_next_field = False

    for idx, line in enumerate(lines):
        # 类名
        m = _CLASS_RE.match(line)
        if m:
            class_name = m.group(1)

        # @TableName
        m = _TABLENAME_RE.search(line)
        if m:
            table_name = m.group(1)

        # @TableField(exist = false) -> 跳过下一个字段
        if _EXIST_FALSE_RE.search(line):
            skip_next_field = True
            continue

        # 字段
        m = _FIELD_RE.match(line)
        if m:
            if skip_next_field:
                skip_next_field = False
                continue
            java_type = m.group(1)
            field_name = m.group(2)

            # 跳过 serialVersionUID
            if field_name == "serialVersionUID":
                continue

            # 提取注释
            comment = _extract_javadoc_above(lines, idx)
            if not comment:
                comment = _extract_inline_comment(line)

            # @TableField 映射
            column_name = ""
            tm = _TABLEFIELD_RE.search(line)
            if tm:
                column_name = tm.group(1)

            fields.append({
                "field_name": field_name,
                "java_type": java_type,
                "column_name": column_name,
                "comment": comment,
            })

    if not class_name:
        return None

    return {
        "class_name": class_name,
        "table_name": table_name,
        "fields": fields,
    }


def collect_entities(domain_dir):
    """收集所有 Java 实体类"""
    entities = []
    domain_path = Path(domain_dir)
    if not domain_path.exists():
        print(f"Warning: Entity directory not found: {domain_dir}", file=sys.stderr)
        return entities

    for java_file in sorted(domain_path.glob("*.java")):
        try:
            entity = parse_java_entity(java_file)
            if entity and entity["fields"]:
                entities.append(entity)
        except Exception as e:
            print(f"Warning: Failed to parse {java_file}: {e}", file=sys.stderr)

    return entities


def get_entity_prefix_groups(entities):
    """按实体类名前缀分组"""
    groups = {}
    for e in entities:
        prefix = _camel_to_prefix(e["class_name"])
        if prefix not in groups:
            groups[prefix] = []
        groups[prefix].append(e)
    return groups


# --- HTML Builders ---

def get_source_class(source):
    """根据注释来源返回 CSS 类名"""
    source = source.strip()
    if source in ("数据库", "database"):
        return "source-db"
    elif source in ("实体类注释", "实体类", "代码注释", "entity"):
        return "source-code"
    elif "JSP" in source:
        return "source-jsp"
    elif "枚举" in source:
        return "source-enum"
    elif "Mapper" in source or "XML" in source:
        return "source-mapper"
    elif "VO" in source:
        return "source-vo"
    elif "AI" in source or "推测" in source or "ai_inferred" in source:
        return "source-ai"
    elif "待补充" in source or "pending" in source:
        return "source-pending"
    return "source-unknown"


def get_prefix_groups(tables):
    """按表名前缀分组"""
    groups = {}
    for t in tables:
        name = t["table_name"]
        parts = name.split("_")
        prefix = parts[0] if len(parts) > 1 else "其他"
        if prefix not in groups:
            groups[prefix] = []
        groups[prefix].append(t)
    return groups


def _build_nav_group(prefix, items_html, count):
    """构建单个导航分组 HTML"""
    return (
        f'<div class="nav-group">'
        f'<div class="nav-group-title" onclick="this.parentElement.classList.toggle(\'collapsed\')">'
        f'<span class="arrow">&#9660;</span> {prefix} ({count})</div>'
        f'<ul class="nav-list">{items_html}</ul></div>'
    )


def build_sidebar_html(db_tables, entity_tables):
    """构建侧边栏 HTML（两个主菜单，按首字母排序）"""
    sections = []

    # 数据库表 - 按表名字母排序
    db_sorted = sorted(db_tables, key=lambda t: t["table_name"].lower())
    db_items = "".join(
        f'<li class="nav-item" data-table="{t["table_name"]}" data-section="db">'
        f'<a href="#">{t["table_name"]}'
        f'<span class="badge">{len(t.get("columns", []))}</span></a></li>'
        for t in db_sorted
    )

    sections.append(
        f'<div class="nav-section" data-section="db">'
        f'<div class="nav-section-title" onclick="toggleSection(this)">'
        f'<span class="arrow">&#9660;</span> 数据库表 ({len(db_tables)})'
        f'<span class="nav-show-all" title="显示全部" onclick="event.stopPropagation();showAllSection(\'db\')">&#8943;</span>'
        f'</div>'
        f'<div class="nav-section-body"><ul class="nav-list flat-list">{db_items}</ul></div>'
        f'</div>'
    )

    # 项目实体 - 按类名字母排序
    if entity_tables:
        ent_sorted = sorted(entity_tables, key=lambda e: e["class_name"].lower())
        ent_items = "".join(
            f'<li class="nav-item" data-table="{e["class_name"]}" data-section="entity">'
            f'<a href="#">{e["class_name"]}'
            f'<span class="badge">{len(e.get("fields", []))}</span></a></li>'
            for e in ent_sorted
        )

        sections.append(
            f'<div class="nav-section" data-section="entity">'
            f'<div class="nav-section-title" onclick="toggleSection(this)">'
            f'<span class="arrow">&#9660;</span> 项目实体 ({len(entity_tables)})'
            f'<span class="nav-show-all" title="显示全部" onclick="event.stopPropagation();showAllSection(\'entity\')">&#8943;</span>'
            f'</div>'
            f'<div class="nav-section-body"><ul class="nav-list flat-list">{ent_items}</ul></div>'
            f'</div>'
        )

    return "\n".join(sections)


def build_stats_html(tables, db_total_tables, slice_tables):
    """构建统计面板 HTML"""
    total_columns = sum(len(t.get("columns", [])) for t in tables)
    doc_tables = len(tables)

    source_counts = {}
    for t in tables:
        for col in t.get("columns", []):
            src = col.get("注释来源", "未知").strip()
            source_counts[src] = source_counts.get(src, 0) + 1

    db_comment_count = source_counts.get("数据库", 0) + source_counts.get("database", 0)
    ai_count = source_counts.get("AI推测", 0) + source_counts.get("ai_inferred", 0)
    pending_count = source_counts.get("待补充", 0) + source_counts.get("pending", 0)
    code_analyzed = sum(v for k, v in source_counts.items()
                        if k not in ('数据库', 'database', 'AI推测', 'ai_inferred', '待补充', 'pending', '未知'))

    stats_parts = [
        f'<div class="stat-card"><div class="stat-value">{db_total_tables}</div><div class="stat-label">数据库总表数</div></div>',
        f'<div class="stat-card"><div class="stat-value">{slice_tables}</div><div class="stat-label">分片表(已跳过)</div></div>',
        f'<div class="stat-card"><div class="stat-value">{doc_tables}</div><div class="stat-label">文档表数</div></div>',
        f'<div class="stat-card"><div class="stat-value">{total_columns}</div><div class="stat-label">总字段数</div></div>',
        f'<div class="stat-card"><div class="stat-value">{db_comment_count}</div><div class="stat-label">数据库注释</div></div>',
        f'<div class="stat-card"><div class="stat-value">{code_analyzed}</div><div class="stat-label">代码分析</div></div>',
        f'<div class="stat-card"><div class="stat-value">{ai_count}</div><div class="stat-label">AI 推测</div></div>',
        f'<div class="stat-card"><div class="stat-value">{pending_count}</div><div class="stat-label">待补充</div></div>',
    ]

    return '<div class="stats-panel">' + "\n".join(stats_parts) + '</div>'


def build_tables_html(tables):
    """构建数据库表详情 HTML"""
    tables_html = []
    for t in tables:
        col_rows = []
        for i, col in enumerate(t.get("columns", []), 1):
            field_name = col.get("字段名", col.get("#", ""))
            col_type = col.get("类型", "")
            nullable = col.get("可空", "")
            default = col.get("默认值", "")
            key = col.get("键", "")
            comment = col.get("注释", "")
            values = col.get("值域", "-")
            source = col.get("注释来源", "")
            source_cls = get_source_class(source)

            key_cls = ""
            if key == "PK":
                key_cls = "key-pk"
            elif key and key != "-":
                key_cls = "key-idx"

            comment_cls = ""
            if "[待补充]" in comment:
                comment_cls = "comment-pending"
            elif source_cls == "source-ai":
                comment_cls = "comment-ai"

            col_rows.append(f"""<tr>
                <td class="col-num">{i}</td>
                <td class="col-name"><code>{field_name}</code></td>
                <td class="col-type">{col_type}</td>
                <td class="col-nullable">{nullable}</td>
                <td class="col-default"><code>{default if default and default != '-' else ''}</code></td>
                <td class="col-key {key_cls}">{key if key and key != '-' else ''}</td>
                <td class="col-comment {comment_cls} editable">{comment}</td>
                <td class="col-values">{values if values and values != '-' else ''}</td>
                <td class="col-source"><span class="source-tag {source_cls}">{source}</span></td>
            </tr>""")

        idx_rows = []
        for idx in t.get("indexes", []):
            idx_rows.append(f"""<tr>
                <td>{idx.get('索引名', '')}</td>
                <td>{idx.get('类型', idx.get('INDEX_TYPE_CN', ''))}</td>
                <td><code>{idx.get('字段', idx.get('COLUMN_NAME', ''))}</code></td>
                <td>{idx.get('唯一', 'NO')}</td>
            </tr>""")

        fk_rows = []
        for fk in t.get("foreign_keys", []):
            fk_rows.append(f"""<tr>
                <td><code>{fk.get('本表字段', '')}</code></td>
                <td>{fk.get('关联表', '')}</td>
                <td><code>{fk.get('关联字段', '')}</code></td>
                <td>{fk.get('关系', '')}</td>
            </tr>""")

        table_comment = t.get("table_comment", "") or "无注释"
        col_count = len(t.get("columns", []))
        idx_count = len(t.get("indexes", []))
        row_count = t.get("row_count", "N/A")

        idx_section = ""
        if idx_rows:
            idx_section = (
                "<h3>索引</h3><table class='detail-table'>"
                "<thead><tr><th>索引名</th><th>类型</th><th>字段</th><th>唯一</th></tr></thead>"
                "<tbody>" + "".join(idx_rows) + "</tbody></table>"
            )

        fk_section = ""
        if fk_rows:
            fk_section = (
                "<h3>外键关系</h3><table class='detail-table'>"
                "<thead><tr><th>本表字段</th><th>关联表</th><th>关联字段</th><th>关系</th></tr></thead>"
                "<tbody>" + "".join(fk_rows) + "</tbody></table>"
            )

        section = f"""
        <div class="table-section" id="table-{t['table_name']}" data-table-name="{t['table_name']}" data-source="db">
            <div class="table-header">
                <h2>{t['table_name']}</h2>
                <span class="table-desc editable">{table_comment}</span>
                <div class="table-meta">
                    <span>字段: {col_count}</span>
                    <span>索引: {idx_count}</span>
                    <span>行数: {row_count}</span>
                </div>
            </div>

            <h3>字段列表</h3>
            <div class="table-scroll">
            <table class="detail-table">
                <thead>
                    <tr>
                        <th>#</th><th>字段名</th><th>类型</th><th>可空</th>
                        <th>默认值</th><th>键</th><th>注释</th><th>值域</th><th>来源</th>
                    </tr>
                </thead>
               <tbody>{"".join(col_rows)}</tbody>
            </table>
            </div>

            {idx_section}
            {fk_section}
        </div>"""
        tables_html.append(section)

    return "".join(tables_html)


def build_entity_tables_html(entities):
    """构建项目实体详情 HTML"""
    tables_html = []
    for e in entities:
        col_rows = []
        for i, f in enumerate(e.get("fields", []), 1):
            field_name = f.get("field_name", "")
            java_type = f.get("java_type", "")
            comment = f.get("comment", "")
            column_name = f.get("column_name", "")

            comment_cls = ""
            if not comment:
                comment_cls = "comment-pending"
                comment = "[待补充]"

            extra = ""
            if column_name:
                extra = f'<span class="source-tag source-code" title="映射列: {column_name}">{column_name}</span>'

            col_rows.append(f"""<tr>
                <td class="col-num">{i}</td>
                <td class="col-name"><code>{field_name}</code></td>
                <td class="col-type">{java_type}</td>
                <td class="col-comment {comment_cls} editable">{comment}</td>
                <td class="col-extra">{extra}</td>
            </tr>""")

        table_name = e.get("table_name", "")
        table_info = f"映射表: {table_name}" if table_name else "无数据库映射"
        col_count = len(e.get("fields", []))

        section = f"""
        <div class="table-section entity-section" id="entity-{e['class_name']}" data-table-name="{e['class_name']}" data-source="entity">
            <div class="table-header">
                <h2>{e['class_name']}</h2>
                <span class="table-desc">{table_info}</span>
                <div class="table-meta">
                    <span>字段: {col_count}</span>
                    <span>来源: Java 实体类</span>
                </div>
            </div>

            <h3>字段列表</h3>
            <div class="table-scroll">
            <table class="detail-table entity-table">
                <thead>
                    <tr>
                        <th>#</th><th>字段名</th><th>Java类型</th><th>注释</th><th>DB列</th>
                    </tr>
                </thead>
               <tbody>{"".join(col_rows)}</tbody>
            </table>
            </div>
        </div>"""
        tables_html.append(section)

    return "".join(tables_html)


def main():
    parser = argparse.ArgumentParser(description="Generate HTML data dictionary")
    parser.add_argument("--input-dir", required=True, help="Directory containing table .md files")
    parser.add_argument("--output", required=True, help="Output HTML file path")
    parser.add_argument("--database", required=True, help="Database name")
    parser.add_argument("--db-total-tables", type=int, default=0, help="Total tables in database")
    parser.add_argument("--slice-tables", type=int, default=0, help="Number of slice tables skipped")
    parser.add_argument("--entities-dir", default="", help="Java entity classes directory")
    parser.add_argument("--api-base", default="", help="API base URL for comment editing")
    args = parser.parse_args()

    print(f"Scanning Markdown files in: {args.input_dir}")
    db_tables = collect_all_tables(args.input_dir)
    print(f"Found {len(db_tables)} database tables")

    entity_tables = []
    if args.entities_dir:
        print(f"Scanning Java entities in: {args.entities_dir}")
        entity_tables = collect_entities(args.entities_dir)
        print(f"Found {len(entity_tables)} entity classes")

    if not TEMPLATE_PATH.exists():
        print(f"Error: Template file not found: {TEMPLATE_PATH}", file=sys.stderr)
        sys.exit(1)

    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        template = f.read()

    db_total = args.db_total_tables if args.db_total_tables > 0 else len(db_tables)
    slice_count = args.slice_tables

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    stats_html = build_stats_html(db_tables, db_total, slice_count)
    sidebar_html = build_sidebar_html(db_tables, entity_tables)
    tables_html = build_tables_html(db_tables)
    entity_html = build_entity_tables_html(entity_tables)

    html = template.replace("__DATABASE__", args.database)
    html = html.replace("__NOW__", now)
    html = html.replace("__STATS_HTML__", stats_html)
    html = html.replace("__SIDEBAR_HTML__", sidebar_html)
    html = html.replace("__TABLES_HTML__", tables_html)
    html = html.replace("__ENTITY_HTML__", entity_html)
    html = html.replace("__API_BASE__", args.api_base)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"HTML generated: {output_path}")
    print(f"Database tables: {len(db_tables)}")
    print(f"Entity classes: {len(entity_tables)}")
    total_cols = sum(len(t.get("columns", [])) for t in db_tables)
    total_ent_fields = sum(len(e.get("fields", [])) for e in entity_tables)
    print(f"Total DB columns: {total_cols}")
    print(f"Total entity fields: {total_ent_fields}")


if __name__ == "__main__":
    main()
