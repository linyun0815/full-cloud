#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SQL 脚本同步管理工具。

用于把上游（开源项目）源码包之间的数据库变更，同步到本项目已有的 MySQL
Navicat 导出脚本中。只修改既有脚本，不创建新的 SQL 文件。

设计约定：
- 文件按 UTF-8 / BOM / 换行风格原样读写；
- 只替换发生变更的 CREATE TABLE 语句块或列定义，其余内容逐字节保留；
- Java DO 能推导出表与列，但索引、初始化数据只有上游 SQL 差异才可靠；
- 推不出的内容进入 needs_review，不写入脚本。

命令：
    check       当前代码与 SQL 脚本的漂移
    diff        对比新旧源码包，列出变更
    sync        执行同步（默认预演，--write 落盘）
    backfill    用当前代码补齐脚本缺失的表（默认预演，--write 落盘）
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

try:  # 可选：更严格的 MySQL 语法校验
    import sqlglot as _sqlglot
except ImportError:  # pragma: no cover
    _sqlglot = None

TOOL_VERSION = 1
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MAPPING = REPO_ROOT / "sql" / "sync" / "mapping.json"
AUDIT_DIR = REPO_ROOT / "sql" / "sync" / "audit"

BASE_COLUMNS = [
    # name, type, nullable, default, comment, extra
    ("creator", "varchar(64)", True, "''", "创建者", ""),
    ("create_time", "datetime", False, "CURRENT_TIMESTAMP", "创建时间", ""),
    ("updater", "varchar(64)", True, "''", "更新者", ""),
    ("update_time", "datetime", False, "CURRENT_TIMESTAMP", "更新时间", "ON UPDATE CURRENT_TIMESTAMP"),
    ("deleted", "bit(1)", False, "b'0'", "是否删除", ""),
]
TENANT_COLUMN = ("tenant_id", "bigint", False, "0", "租户编号", "")

TYPE_CATEGORY = {
    "bigint": "int",
    "int": "int",
    "integer": "int",
    "smallint": "int",
    "mediumint": "int",
    "tinyint": "int",
    "bit": "bool",
    "boolean": "bool",
    "bool": "bool",
    "varchar": "string",
    "char": "string",
    "longvarchar": "string",
    "text": "text",
    "tinytext": "text",
    "mediumtext": "text",
    "longtext": "text",
    "json": "json",
    "decimal": "decimal",
    "numeric": "decimal",
    "double": "float",
    "float": "float",
    "real": "float",
    "datetime": "datetime",
    "timestamp": "datetime",
    "date": "date",
    "time": "time",
    "year": "year",
    "blob": "blob",
    "tinyblob": "blob",
    "mediumblob": "blob",
    "longblob": "blob",
    "varbinary": "blob",
    "binary": "blob",
}

JAVA_TYPE_MAP = {
    "Long": "bigint",
    "long": "bigint",
    "Integer": "int",
    "int": "int",
    "Short": "smallint",
    "short": "smallint",
    "Byte": "tinyint",
    "byte": "tinyint",
    "String": "varchar(255)",
    "Boolean": "bit(1)",
    "boolean": "bit(1)",
    "BigDecimal": "decimal(24, 6)",
    "Double": "double",
    "double": "double",
    "Float": "double",
    "float": "double",
    "LocalDateTime": "datetime",
    "LocalDate": "date",
    "LocalTime": "time",
    "Instant": "datetime",
    "OffsetDateTime": "datetime",
    "Date": "datetime",
    "byte[]": "mediumblob",
    "Byte[]": "mediumblob",
}

BASE_FIELD_NAMES = {"creator", "create_time", "updater", "update_time", "deleted", "tenant_id"}


# ---------------------------------------------------------------------------
# 基础数据结构
# ---------------------------------------------------------------------------


@dataclass
class Column:
    name: str
    type: str
    definition: str
    nullable: bool = True
    default: Optional[str] = None
    comment: Optional[str] = None
    extra: str = ""
    charset: Optional[str] = None
    collate: Optional[str] = None
    line_index: Optional[int] = None
    origin: str = "sql"
    review: Optional[str] = None

    def category(self) -> str:
        return TYPE_CATEGORY.get(normalize_type_base(self.type), "other")

    def signature(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": normalize_type(self.type),
            "nullable": self.nullable,
            "default": normalize_default(self.default),
            "comment": self.comment or "",
            "extra": normalize_space(self.extra),
        }


@dataclass
class IndexDef:
    name: str
    columns: list[str]
    unique: bool
    kind: str
    definition: str
    line_index: Optional[int] = None

    def signature(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "columns": [c.lower() for c in self.columns],
            "unique": self.unique,
            "kind": self.kind,
        }


@dataclass
class TableSchema:
    name: str
    columns: list[Column] = field(default_factory=list)
    indexes: list[IndexDef] = field(default_factory=list)
    comment: str = ""
    options_tail: str = ""
    header_start: int = -1
    create_start: int = -1
    create_end: int = -1
    records_start: int = -1
    records_end: int = -1
    inserts: list[str] = field(default_factory=list)
    source_file: str = ""
    origin: str = "sql"
    review: list[str] = field(default_factory=list)

    def column(self, name: str) -> Optional[Column]:
        low = name.lower()
        for c in self.columns:
            if c.name.lower() == low:
                return c
        return None

    def pk(self) -> list[str]:
        for idx in self.indexes:
            if idx.kind == "primary":
                return idx.columns
        return []

    def signature(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "comment": self.comment,
            "columns": [c.signature() for c in self.columns],
            "indexes": sorted((i.signature() for i in self.indexes), key=lambda x: (x["kind"], x["name"])),
        }

    def signature_hash(self) -> str:
        return sha256_json(self.signature())


@dataclass
class DoField:
    name: str
    java_type: str
    comment: str = ""
    is_json: bool = False
    exist: bool = True
    column_name: Optional[str] = None

    def column(self) -> str:
        if self.column_name:
            return self.column_name
        return camel_to_snake(self.name)


@dataclass
class DoTable:
    name: str
    class_name: str
    module: str
    fields: list[DoField]
    parent: Optional[str]
    comment: str = ""
    source_file: str = ""

    def column_names(self) -> list[str]:
        return [f.column() for f in self.fields if f.exist]


@dataclass
class Routine:
    kind: str  # procedure / function / view / trigger
    name: str
    raw: str
    start: int = -1
    end: int = -1
    source_file: str = ""

    def signature(self) -> str:
        # 去掉 DEFINER、多余空白后再比较，避免导出账号不同造成误报
        text = re.sub(r"DEFINER\s*=\s*\S+\s+", "", self.raw, flags=re.I)
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        return sha256_text(normalize_space(text))


@dataclass
class SqlDocument:
    path: Path
    text: str
    bom: bool = False
    newline: str = "\n"
    lines: list[str] = field(default_factory=list)
    tables: dict[str, TableSchema] = field(default_factory=dict)
    routines: dict[str, Routine] = field(default_factory=dict)
    header_end: int = 0
    tail_start: int = -1
    readonly: bool = False

    @property
    def relpath(self) -> str:
        try:
            return self.path.resolve().relative_to(REPO_ROOT).as_posix()
        except ValueError:
            return self.path.as_posix()

    def render(self) -> str:
        return "".join(self.lines)


@dataclass
class Change:
    action: str  # create_table / alter_table / alter_columns / drop_table / data
    table: str
    origin: str  # upstream_sql / code_do / backfill
    target_file: Optional[str] = None
    old_table: Optional[TableSchema] = None
    new_table: Optional[TableSchema] = None
    column_changes: list[dict[str, Any]] = field(default_factory=list)
    index_changes: list[dict[str, Any]] = field(default_factory=list)
    data_added: int = 0
    data_removed: int = 0
    note: str = ""
    needs_review: list[str] = field(default_factory=list)
    change_hash: str = ""
    routine: Optional[Routine] = None
    old_routine: Optional[Routine] = None
    new_inserts: list[str] = field(default_factory=list)
    status: str = ""

    def describe(self) -> str:
        if self.action == "create_table":
            return f"新增表 {self.table}"
        if self.action == "drop_table":
            return f"删除表 {self.table}"
        if self.action == "alter_columns":
            return f"字段变更 {self.table}（{len(self.column_changes)} 项）"
        if self.action == "alter_table":
            return f"表结构变更 {self.table}（上游 SQL）"
        if self.action == "create_routine":
            return f"新增 {self.routine.kind if self.routine else '例程'} {self.table}"
        if self.action == "alter_routine":
            return f"修改 {self.routine.kind if self.routine else '例程'} {self.table}"
        if self.action == "drop_routine":
            return f"删除 {self.old_routine.kind if self.old_routine else '例程'} {self.table}"
        return f"{self.action} {self.table}"

    def compute_hash(self) -> str:
        payload = {
            "action": self.action,
            "table": self.table,
            "origin": self.origin,
            "new": self.new_table.signature() if self.new_table else None,
            "routine": self.routine.signature() if self.routine else None,
            "column_changes": self.column_changes,
        }
        self.change_hash = sha256_json(payload)[:16]
        return self.change_hash


# ---------------------------------------------------------------------------
# 通用工具
# ---------------------------------------------------------------------------


def read_text(path: Path) -> tuple[str, bool, str]:
    raw = path.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    newline = "\r\n" if "\r\n" in text else "\n"
    return text, bom, newline


def write_text(path: Path, text: str, bom: bool) -> None:
    data = text.encode("utf-8")
    if bom and not data.startswith(b"\xef\xbb\xbf"):
        data = b"\xef\xbb\xbf" + data
    tmp = path.with_name(path.name + ".sqlsync-tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def sha256_json(value: Any) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_space(value: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def normalize_type(value: str) -> str:
    v = normalize_space(value).lower()
    v = re.sub(r"\s*\(\s*", "(", v)
    v = re.sub(r"\s*,\s*", ",", v)
    v = re.sub(r"\s*\)", ")", v)
    v = re.sub(r"\s+unsigned", " unsigned", v)
    return v


def normalize_type_base(value: str) -> str:
    return re.match(r"([a-z]+)", normalize_type(value)).group(1) if value else ""


def normalize_default(value: Optional[str]) -> str:
    if value is None:
        return ""
    return normalize_space(value).lower()


def camel_to_snake(name: str) -> str:
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def snake_to_pascal(name: str) -> str:
    return "".join(p.capitalize() for p in name.split("_"))


def escape_sql_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "''")


def now_local() -> datetime:
    return datetime.now().astimezone()


def timestamp_iso() -> str:
    return now_local().isoformat(timespec="seconds")


def sync_id() -> str:
    return now_local().strftime("%Y%m%d-%H%M%S-%f")


SQL_DATE_IN_NAME_RE = re.compile(r"(?<!\d)(\d{2,4})-(\d{2})-(\d{2})(?=\.sql$)", re.I)


def dated_sql_filename(name: str, when: Optional[datetime] = None) -> str:
    """把文件名中的 YYYY-MM-DD 替换为 when 的日期；没有日期则原样返回。"""
    when = when or now_local()
    match = SQL_DATE_IN_NAME_RE.search(name)
    if not match:
        return name
    return name[: match.start()] + when.strftime("%Y-%m-%d") + name[match.end() :]


def plan_sql_renames(rels: Iterable[str], when: Optional[datetime] = None) -> tuple[dict[str, str], list[str]]:
    """计算需要改名的脚本；返回 {旧相对路径: 新相对路径} 和错误列表。"""
    when = when or now_local()
    renames: dict[str, str] = {}
    errors: list[str] = []
    planned_targets: set[str] = set()
    for rel in sorted(set(rels)):
        path = Path(rel)
        new_name = dated_sql_filename(path.name, when)
        if new_name == path.name:
            continue
        new_rel = (path.parent / new_name).as_posix()
        if new_rel in planned_targets:
            errors.append(f"多个脚本会改名为同一文件: {new_rel}")
            continue
        target = REPO_ROOT / new_rel
        if target.exists():
            errors.append(f"目标文件已存在，未改名: {new_rel}")
            continue
        planned_targets.add(new_rel)
        renames[rel] = new_rel
    return renames, errors


def apply_sql_renames(renames: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    applied: dict[str, str] = {}
    errors: list[str] = []
    for old_rel, new_rel in sorted(renames.items()):
        old_path = REPO_ROOT / old_rel
        new_path = REPO_ROOT / new_rel
        if not old_path.exists():
            errors.append(f"源文件不存在，未改名: {old_rel}")
            continue
        if new_path.exists():
            errors.append(f"目标文件已存在，未改名: {new_rel}")
            continue
        try:
            old_path.rename(new_path)
            applied[old_rel] = new_rel
        except OSError as exc:
            errors.append(f"改名失败 {old_rel} -> {new_rel}: {exc}")
    return applied, errors


def update_mapping_paths(mapping: "Mapping", renames: dict[str, str]) -> None:
    if not renames:
        return
    for module in mapping.data.get("modules", {}).values():
        files = module.get("files", [])
        module["files"] = [renames.get(rel, rel) for rel in files]
    explicit = mapping.data.get("explicit_tables", {})
    for table, rel in list(explicit.items()):
        explicit[table] = renames.get(rel, rel)
    files_data = mapping.data.get("files", {})
    if files_data:
        mapping.data["files"] = {renames.get(rel, rel): entry for rel, entry in files_data.items()}


def rename_payload(renames: dict[str, str]) -> list[dict[str, str]]:
    return [{"from": old, "to": new} for old, new in sorted(renames.items())]


def detect_module_from_path(path: Path) -> Optional[str]:
    text = path.as_posix()
    m = re.search(r"(?:full|yudao)-module-([a-z0-9-]+)", text)
    return m.group(1) if m else None


def project_version() -> Optional[str]:
    pom = REPO_ROOT / "pom.xml"
    if not pom.exists():
        return None
    m = re.search(r"<revision>\s*([^<]+?)\s*</revision>", pom.read_text(encoding="utf-8", errors="replace"))
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# SQL DDL 解析
# ---------------------------------------------------------------------------


def split_top_level(text: str, delimiter: str = ",") -> list[tuple[int, int]]:
    """按顶层分隔符切分，忽略括号、引号、反引号内部的分隔符。"""
    spans: list[tuple[int, int]] = []
    start = 0
    depth = 0
    quote: Optional[str] = None
    i = 0
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                if i + 1 < len(text) and text[i + 1] == quote:
                    i += 2
                    continue
                quote = None
        else:
            if ch in "'\"`":
                quote = ch
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == delimiter and depth == 0:
                spans.append((start, i))
                start = i + 1
        i += 1
    spans.append((start, len(text)))
    return spans


def strip_definition(text: str) -> str:
    return text.strip().rstrip(",").strip()


def extract_quoted(text: str, keyword: str) -> Optional[str]:
    m = re.search(keyword + r"\s*(?:=\s*)?'((?:\\.|''|[^'])*)'", text, re.I)
    if not m:
        return None
    return m.group(1).replace("''", "'").replace("\\'", "'")


def parse_column(definition: str) -> Optional[Column]:
    if not definition.startswith("`"):
        return None
    m = re.match(
        r"^`(?P<name>[^`]+)`\s+(?P<type>[A-Za-z]+(?:\s*\([^)]*\))?(?:\s+UNSIGNED)?)(?P<rest>.*)$",
        definition,
        re.I | re.S,
    )
    if not m:
        return None
    name = m.group("name")
    typ = normalize_space(m.group("type"))
    rest = m.group("rest")
    nullable = not re.search(r"\bNOT\s+NULL\b", rest, re.I)
    charset = None
    collate = None
    charset_m = re.search(r"CHARACTER\s+SET\s+(\w+)", rest, re.I)
    if charset_m:
        charset = charset_m.group(1)
    collate_m = re.search(r"COLLATE\s+(\w+)", rest, re.I)
    if collate_m:
        collate = collate_m.group(1)
    default = None
    default_m = re.search(
        r"\bDEFAULT\s+(b'[01]'|NULL|'(?:\\.|''|[^'])*'|CURRENT_TIMESTAMP(?:\(\s*\d*\s*\))?(?:\s+ON\s+UPDATE\s+CURRENT_TIMESTAMP(?:\(\s*\d*\s*\))?)?|[\w.\-+]+)",
        rest,
        re.I,
    )
    if default_m:
        default = default_m.group(1)
    comment = extract_quoted(rest, "COMMENT")
    extra = ""
    if re.search(r"\bAUTO_INCREMENT\b", rest, re.I):
        extra = "AUTO_INCREMENT"
    if re.search(r"\bON\s+UPDATE\s+CURRENT_TIMESTAMP", rest, re.I):
        extra = (extra + " ON UPDATE CURRENT_TIMESTAMP").strip()
    return Column(
        name=name,
        type=typ,
        definition=definition,
        nullable=nullable,
        default=default,
        comment=comment,
        extra=extra,
        charset=charset,
        collate=collate,
    )


def parse_index(definition: str) -> Optional[IndexDef]:
    text = definition.strip()
    if re.match(r"^PRIMARY\s+KEY", text, re.I):
        cols = re.findall(r"`([^`]+)`", text)
        return IndexDef("PRIMARY", cols, True, "primary", text)
    m = re.match(r"^(?P<unique>UNIQUE\s+)?(?P<kind>INDEX|KEY)\s+`(?P<name>[^`]+)`\s*\((?P<cols>.*)\)", text, re.I | re.S)
    if m:
        cols = re.findall(r"`([^`]+)`", m.group("cols"))
        return IndexDef(
            m.group("name"),
            cols,
            bool(m.group("unique")),
            "unique" if m.group("unique") else "index",
            text,
        )
    if re.match(r"^CONSTRAINT\b", text, re.I):
        m2 = re.match(r"^CONSTRAINT\s+`(?P<name>[^`]+)`\s+(?P<body>.*)$", text, re.I | re.S)
        if m2:
            cols = re.findall(r"`([^`]+)`", m2.group("body"))
            return IndexDef(m2.group("name"), cols, False, "constraint", text)
    return None


def parse_create_statement(inner: str, line_offset: int) -> tuple[list[Column], list[IndexDef]]:
    columns: list[Column] = []
    indexes: list[IndexDef] = []
    for start, end in split_top_level(inner):
        raw = inner[start:end]
        definition = strip_definition(raw)
        if not definition:
            continue
        # 计算该定义所在行（现有导出中每个定义占一行）
        line_index = line_offset + inner[:start].count("\n")
        if definition.startswith("`"):
            col = parse_column(definition)
            if col:
                col.line_index = line_index
                columns.append(col)
        else:
            idx = parse_index(definition)
            if idx:
                idx.line_index = line_index
                indexes.append(idx)
    return columns, indexes


def parse_table_options(closing_line: str) -> tuple[str, str]:
    """返回 (去掉结尾分号的表选项, 表注释)。"""
    body = closing_line.strip()
    if body.startswith(")"):
        body = body[1:].strip()
    if body.endswith(";"):
        body = body[:-1].rstrip()
    comment = extract_quoted(body, "COMMENT") or ""
    return body, comment


ROUTINE_RE = re.compile(
    r"^\s*CREATE\s+(?:OR\s+REPLACE\s+)?(?:DEFINER\s*=\s*[^\s]+\s+)?"
    r"(?:ALGORITHM\s*=\s*\w+\s+)?(?:SQL\s+SECURITY\s+\w+\s+)?"
    r"(PROCEDURE|FUNCTION|TRIGGER|VIEW)\s+`?([A-Za-z0-9_$.]+)`?",
    re.I,
)


def parse_routines(lines: list[str], relpath: str) -> dict[str, Routine]:
    routines: dict[str, Routine] = {}
    i = 0
    while i < len(lines):
        m = ROUTINE_RE.match(lines[i])
        if not m:
            i += 1
            continue
        kind = m.group(1).lower()
        name = m.group(2)
        start = i
        if start > 0 and lines[start - 1].strip().upper().startswith("DELIMITER"):
            start -= 1
        end = i
        if kind == "view":
            # 视图以分号结束
            depth = 0
            quote: Optional[str] = None
            while end < len(lines):
                line = lines[end]
                pos = 0
                while pos < len(line):
                    ch = line[pos]
                    if quote:
                        if ch == "\\":
                            pos += 2
                            continue
                        if ch == quote:
                            if pos + 1 < len(line) and line[pos + 1] == quote:
                                pos += 2
                                continue
                            quote = None
                    else:
                        if ch in "'\"`":
                            quote = ch
                        elif ch == "(":
                            depth += 1
                        elif ch == ")":
                            depth -= 1
                    pos += 1
                if depth == 0 and line.rstrip().endswith(";"):
                    break
                if end > i and re.match(r"^-- Table structure for ", line.strip()):
                    end -= 1
                    break
                end += 1
        else:
            while end + 1 < len(lines):
                nxt = lines[end + 1]
                if re.match(r"^\s*END\s*(?:\$\$|;;|//)?\s*;?\s*$", nxt, re.I):
                    end += 1
                    # 一并带上导出脚本中的 DELIMITER ; 结束行
                    if end + 1 < len(lines) and lines[end + 1].strip().upper().startswith("DELIMITER ;"):
                        end += 1
                    break
                if nxt.strip().upper().startswith("DELIMITER ;"):
                    end += 1
                    break
                if re.match(r"^-- Table structure for ", nxt.strip()):
                    break
                end += 1
        raw = "".join(lines[start : end + 1])
        routines[name.lower()] = Routine(kind=kind, name=name, raw=raw, start=start, end=end, source_file=relpath)
        i = end + 1
    return routines


def parse_sql_text(text: str, path: Path, readonly: bool = False) -> SqlDocument:
    doc = SqlDocument(path=path, text=text, lines=text.splitlines(keepends=True), readonly=readonly)
    lines = doc.lines
    i = 0
    while i < len(lines):
        m = re.match(r"^-- Table structure for ([A-Za-z0-9_$]+)\s*$", lines[i].strip())
        if not m:
            i += 1
            continue
        name = m.group(1)
        header_start = i
        if i > 0 and re.match(r"^-- -{8,}\s*$", lines[i - 1].strip()):
            header_start = i - 1
        j = i + 1
        while j < len(lines) and not lines[j].lstrip().upper().startswith("CREATE TABLE"):
            j += 1
        if j >= len(lines):
            i += 1
            continue
        create_start = j
        open_line = lines[j].find("(")
        depth = 0
        quote: Optional[str] = None
        k = j
        create_end = -1
        seen_open = False
        while k < len(lines):
            line = lines[k]
            m_idx = 0
            while m_idx < len(line):
                ch = line[m_idx]
                if quote:
                    if ch == "\\":
                        m_idx += 2
                        continue
                    if ch == quote:
                        if m_idx + 1 < len(line) and line[m_idx + 1] == quote:
                            m_idx += 2
                            continue
                        quote = None
                else:
                    if ch in "'\"`":
                        quote = ch
                    elif ch == "(":
                        depth += 1
                        seen_open = True
                    elif ch == ")":
                        depth -= 1
                m_idx += 1
            if seen_open and depth <= 0 and line.rstrip().endswith(";"):
                create_end = k
                break
            k += 1
        if create_end < 0:
            i += 1
            continue
        inner = "".join(lines[create_start + 1 : create_end])
        columns, indexes = parse_create_statement(inner, create_start + 1)
        options_tail, comment = parse_table_options(lines[create_end])
        table = TableSchema(
            name=name,
            columns=columns,
            indexes=indexes,
            comment=comment,
            options_tail=options_tail,
            header_start=header_start,
            create_start=create_start,
            create_end=create_end,
            source_file=doc.relpath,
        )
        # records 段
        r = create_end + 1
        while r < len(lines):
            if re.match(r"^-- Table structure for ", lines[r].strip()):
                break
            if re.match(r"^-- Records of ([A-Za-z0-9_$]+)\s*$", lines[r].strip()):
                records_start = r
                if r > 0 and re.match(r"^-- -{8,}\s*$", lines[r - 1].strip()):
                    records_start = r - 1
                rr = r + 1
                while rr < len(lines) and not lines[rr].strip().upper().startswith("COMMIT;"):
                    if lines[rr].strip().upper().startswith("INSERT INTO"):
                        table.inserts.append(lines[rr].strip())
                    rr += 1
                table.records_start = records_start
                table.records_end = rr
                break
            r += 1
        doc.tables[name] = table
        i = max(create_end, j) + 1
    doc.routines = parse_routines(doc.lines, doc.relpath)
    for index, line in enumerate(doc.lines):
        if line.strip().upper().startswith("SET FOREIGN_KEY_CHECKS = 1"):
            doc.tail_start = index
            break
    return doc


def load_sql_document(path: Path, readonly: bool = False) -> SqlDocument:
    text, bom, newline = read_text(path)
    doc = parse_sql_text(text, path, readonly=readonly)
    doc.bom = bom
    doc.newline = newline
    return doc


def load_local_documents(mapping: Mapping) -> dict[str, SqlDocument]:
    docs: dict[str, SqlDocument] = {}
    root = REPO_ROOT / mapping.sql_root
    readonly = set(mapping.readonly_files)
    for path in sorted(root.rglob("*.sql")):
        rel = path.resolve().relative_to(REPO_ROOT).as_posix()
        try:
            docs[rel] = load_sql_document(path, readonly=rel in readonly)
        except UnicodeDecodeError as exc:
            print(f"[warn] 跳过无法按 UTF-8 读取的文件 {rel}: {exc}", file=sys.stderr)
    return docs


def index_local_tables(docs: dict[str, SqlDocument]) -> dict[str, tuple[str, TableSchema]]:
    result: dict[str, tuple[str, TableSchema]] = {}
    for rel, doc in docs.items():
        for table in doc.tables.values():
            if table.name in result:
                print(
                    f"[warn] 表 {table.name} 同时出现在 {result[table.name][0]} 和 {rel}",
                    file=sys.stderr,
                )
                continue
            result[table.name] = (rel, table)
    return result


# ---------------------------------------------------------------------------
# Java DO 解析
# ---------------------------------------------------------------------------

TABLE_NAME_RE = re.compile(r"@TableName\s*\(\s*(?:value\s*=\s*)?\"([^\"]+)\"")
CLASS_RE = re.compile(r"\bclass\s+([A-Za-z0-9_]+)(?:<[^>]*>)?\s*(?:extends\s+([A-Za-z0-9_.]+))?")
FIELD_RE = re.compile(r"^private\s+(?!static\b|final\b)([A-Za-z0-9_$.<>,\[\] ]+?)\s+([A-Za-z0-9_]+)\s*;\s*$")
EXIST_FALSE_RE = re.compile(r"@TableField\s*\([^)]*exist\s*=\s*false", re.S)
TYPE_HANDLER_RE = re.compile(r"@TableField\s*\([^)]*typeHandler\s*=", re.S)
TABLE_FIELD_VALUE_RE = re.compile(r"@TableField\s*\(\s*(?:value\s*=\s*)?\"([^\"]+)\"")


def clean_javadoc(lines: list[str]) -> str:
    if not lines:
        return ""
    cleaned: list[str] = []
    for raw in lines:
        s = raw.strip()
        s = re.sub(r"^/\*\*+", "", s)
        s = re.sub(r"\*/$", "", s)
        s = re.sub(r"^\*\s?", "", s)
        if not s or s.startswith("@"):
            continue
        cleaned.append(s)
    text = " ".join(cleaned)
    # 只取第一段摘要，避免把关联说明、枚举说明全部塞进数据库注释
    text = re.split(r"<p\s*/?>", text, maxsplit=1, flags=re.I)[0]
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.I)
    text = re.sub(r"\{@link\s+([^}]+)\}", r"\1", text)
    text = re.sub(r"\{@code\s+([^}]+)\}", r"\1", text)
    text = re.sub(r"\{@[^}]+\}", "", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = normalize_space(text)
    text = text.rstrip("。；; ")
    return text


def parse_do_file(path: Path) -> Optional[DoTable]:
    text = path.read_text(encoding="utf-8", errors="replace")
    tm = TABLE_NAME_RE.search(text)
    if not tm:
        return None
    cm = CLASS_RE.search(text)
    if not cm:
        return None
    class_name = cm.group(1)
    parent = cm.group(2)
    module = detect_module_from_path(path)
    if not module:
        return None
    # 类注释
    pre = text[: cm.start()]
    class_doc_match = re.findall(r"/\*\*(.*?)\*/", pre, re.S)
    class_comment = clean_javadoc(class_doc_match[-1].splitlines()) if class_doc_match else ""
    # 类体
    body_start = text.find("{", cm.end())
    if body_start < 0:
        return None
    fields: list[DoField] = []
    depth = 0
    javadoc: list[str] = []
    in_javadoc = False
    pending_exist_false = False
    pending_json = False
    pending_column: Optional[str] = None
    for line in text[body_start:].splitlines():
        stripped = line.strip()
        if in_javadoc:
            javadoc.append(stripped)
            if "*/" in stripped:
                in_javadoc = False
            continue
        if stripped.startswith("/**"):
            javadoc = [stripped]
            if "*/" not in stripped:
                in_javadoc = True
            continue
        if depth == 1:
            if stripped.startswith("@"):
                if EXIST_FALSE_RE.search(stripped) or (
                    "exist" in stripped and "false" in stripped and not pending_exist_false
                ):
                    pending_exist_false = True
                if TYPE_HANDLER_RE.search(stripped):
                    pending_json = True
                fm = TABLE_FIELD_VALUE_RE.search(stripped)
                if fm:
                    pending_column = fm.group(1)
                # 注解可能跨行，简单累积到下一行
            fm = FIELD_RE.match(stripped)
            if fm:
                ftype = normalize_space(fm.group(1))
                fname = fm.group(2)
                raw_type = ftype
                is_json = pending_json or bool(re.search(r"Jackson\w*TypeHandler", stripped))
                fields.append(
                    DoField(
                        name=fname,
                        java_type=raw_type,
                        comment=clean_javadoc(javadoc),
                        is_json=is_json,
                        exist=not pending_exist_false,
                        column_name=pending_column,
                    )
                )
                javadoc = []
                pending_exist_false = False
                pending_json = False
                pending_column = None
        depth += stripped.count("{") - stripped.count("}")
    return DoTable(
        name=tm.group(1),
        class_name=class_name,
        module=module,
        fields=fields,
        parent=parent,
        comment=class_comment,
        source_file=path.as_posix(),
    )


def load_do_tables(root: Path) -> dict[str, DoTable]:
    result: dict[str, DoTable] = {}
    for path in sorted(root.rglob("*.java")):
        if "dal" not in path.parts or "dataobject" not in path.parts:
            continue
        if not path.name.endswith("DO.java"):
            continue
        try:
            table = parse_do_file(path)
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] 解析 {path} 失败: {exc}", file=sys.stderr)
            continue
        if table:
            if table.name in result:
                print(f"[warn] 表 {table.name} 对应多个 DO，保留 {result[table.name].source_file}", file=sys.stderr)
                continue
            result[table.name] = table
    return result


# ---------------------------------------------------------------------------
# 类型推导与风格
# ---------------------------------------------------------------------------


@dataclass
class StyleContext:
    charset: str = "utf8mb4"
    collate: str = "utf8mb4_unicode_ci"
    columns_by_name: dict[str, Column] = field(default_factory=dict)
    column_types_by_name: dict[str, dict[str, int]] = field(default_factory=dict)
    varchar_lengths: list[int] = field(default_factory=list)

    @classmethod
    def from_tables(cls, tables: Iterable[TableSchema]) -> "StyleContext":
        ctx = cls()
        lengths: list[int] = []
        for table in tables:
            for col in table.columns:
                key = col.name.lower()
                ctx.columns_by_name.setdefault(key, col)
                ctx.column_types_by_name.setdefault(key, {})
                ctx.column_types_by_name[key][col.type] = ctx.column_types_by_name[key].get(col.type, 0) + 1
                m = re.match(r"varchar\((\d+)\)", normalize_type(col.type))
                if m:
                    lengths.append(int(m.group(1)))
        ctx.varchar_lengths = sorted(lengths)
        return ctx

    def preferred_varchar_length(self) -> int:
        if not self.varchar_lengths:
            return 255
        # 取中位数，避免少数超长字段（如 URL）带偏
        return self.varchar_lengths[len(self.varchar_lengths) // 2]

    def preferred_type(self, field_name: str, java_type: str, is_json: bool) -> tuple[str, Optional[str], Optional[str]]:
        low = field_name.lower()
        wanted = TYPE_CATEGORY.get(normalize_type_base(JAVA_TYPE_MAP.get(java_type, "")), "other")
        if is_json:
            candidates = self.column_types_by_name.get(low, {})
            for type_name, _count in sorted(candidates.items(), key=lambda x: -x[1]):
                if TYPE_CATEGORY.get(normalize_type_base(type_name), "other") in ("string", "text"):
                    existing = self.columns_by_name.get(low)
                    return type_name, (existing.charset if existing else None), (existing.collate if existing else None)
            return "json", None, None
        if java_type == "String":
            if low.endswith("_url") or low == "url":
                return "varchar(1024)", self.charset, self.collate
            if low in (
                "text",
                "content",
                "formula",
                "lyric",
                "generated_content",
                "original_content",
                "introduction",
                "idea",
                "outline",
                "source_material",
                "worldbuilding",
                "revision_note",
                "source_text",
                "scene_text",
                "input_text",
                "sample_text",
                "voice_description",
                "crowd_description",
            ) or "prompt" in low:
                return "text", None, None
            if low.endswith("error_message") or low.endswith("message"):
                return "varchar(1024)", self.charset, self.collate
            if low in ("aliases", "change_reason"):
                return "varchar(255)", self.charset, self.collate
            if low in ("description", "remark", "system_message"):
                return "varchar(1024)", self.charset, self.collate
        candidates = self.column_types_by_name.get(low, {})
        if candidates and wanted != "other":
            # 同名历史列中出现次数最多的类型，且与新字段类型大类一致
            best = None
            best_count = -1
            for type_name, count in candidates.items():
                if TYPE_CATEGORY.get(normalize_type_base(type_name), "other") == wanted and count > best_count:
                    best, best_count = type_name, count
            if best:
                existing = self.columns_by_name.get(low)
                return best, (existing.charset if existing and normalize_type(existing.type) == normalize_type(best) else None), (
                    existing.collate if existing and normalize_type(existing.type) == normalize_type(best) else None
                )
        base_type = JAVA_TYPE_MAP.get(java_type)
        if not base_type:
            return "", None, None
        if base_type.startswith("varchar("):
            base_type = f"varchar({self.preferred_varchar_length()})"
        return base_type, self.charset, self.collate


def field_to_column(field: DoField, style: StyleContext, table_name: str) -> Optional[Column]:
    java_type = re.sub(r"<.*>$", "", field.java_type).strip()
    col_name = field.column()
    if not field.exist:
        return None
    if col_name == "id":
        definition = f"`id` bigint NOT NULL AUTO_INCREMENT"
        if field.comment:
            definition += f" COMMENT '{escape_sql_string(field.comment)}'"
        return Column(
            "id",
            "bigint",
            definition,
            nullable=False,
            default=None,
            comment=field.comment or None,
            extra="AUTO_INCREMENT",
            origin="code",
        )
    if col_name in BASE_FIELD_NAMES:
        return None  # 由公共字段统一生成
    typ, charset, collate = style.preferred_type(col_name, java_type, field.is_json)
    review = None
    if not typ:
        typ = "varchar(255)"
        review = f"无法从 Java 类型 {field.java_type} 推导 MySQL 类型，暂用 {typ}"
    if col_name.startswith("is_") or java_type in ("Boolean", "boolean"):
        typ = "bit(1)"
    nullable = True
    default = "NULL"
    extra = ""
    if java_type in ("Boolean", "boolean"):
        nullable = False
        default = "b'0'"
    if typ.startswith("json"):
        default = "NULL"
    definition = f"`{col_name}` {typ}"
    if charset and normalize_type_base(typ) in ("varchar", "char", "text", "tinytext", "mediumtext", "longtext"):
        definition += f" CHARACTER SET {charset} COLLATE {collate or style.collate}"
    if nullable:
        definition += " NULL DEFAULT NULL"
    else:
        definition += " NOT NULL"
        if default:
            definition += f" DEFAULT {default}"
    if extra:
        definition += f" {extra}"
    if field.comment:
        definition += f" COMMENT '{escape_sql_string(field.comment)}'"
    return Column(
        name=col_name,
        type=typ,
        definition=definition,
        nullable=nullable,
        default=default if nullable else default,
        comment=field.comment or None,
        extra=extra,
        charset=charset,
        collate=collate,
        origin="code",
        review=review,
    )


def base_columns_for(do_table: DoTable, style: StyleContext) -> list[Column]:
    specs = list(BASE_COLUMNS)
    if do_table.parent and "TenantBaseDO" in do_table.parent:
        specs = specs + [TENANT_COLUMN]
    columns: list[Column] = []
    for name, typ, nullable, default, comment, extra in specs:
        definition = f"`{name}` {typ}"
        if normalize_type_base(typ) in ("varchar", "char"):
            definition += f" CHARACTER SET {style.charset} COLLATE {style.collate}"
        if nullable:
            definition += f" NULL DEFAULT {default}"
        else:
            definition += f" NOT NULL DEFAULT {default}"
        if extra:
            definition += f" {extra}"
        definition += f" COMMENT '{comment}'"
        columns.append(
            Column(
                name=name,
                type=typ,
                definition=definition,
                nullable=nullable,
                default=default,
                comment=comment,
                extra=extra,
                charset=style.charset if normalize_type_base(typ) in ("varchar", "char") else None,
                collate=style.collate if normalize_type_base(typ) in ("varchar", "char") else None,
                origin="base",
            )
        )
    return columns


def derive_table(do_table: DoTable, style: StyleContext) -> TableSchema:
    columns: list[Column] = []
    seen: set[str] = set()
    for field in do_table.fields:
        col = field_to_column(field, style, do_table.name)
        if not col or col.name in seen:
            continue
        seen.add(col.name)
        columns.append(col)
    # id 必须在最前
    id_col = next((c for c in columns if c.name == "id"), None)
    if id_col is None:
        id_col = Column(
            "id",
            "bigint",
            "`id` bigint NOT NULL AUTO_INCREMENT COMMENT '编号'",
            nullable=False,
            comment="编号",
            extra="AUTO_INCREMENT",
            origin="code",
        )
        columns.insert(0, id_col)
    else:
        columns.remove(id_col)
        columns.insert(0, id_col)
    for col in base_columns_for(do_table, style):
        if col.name not in seen:
            columns.append(col)
            seen.add(col.name)
    table_comment = do_table.comment or do_table.class_name
    table_comment = re.sub(r"\bDO\b\s*(?=[：:])", "", table_comment)
    table_comment = re.sub(r"\s*DO\s*$", "", table_comment)
    table_comment = re.sub(r"\s+([：:])", r"\1", table_comment).strip()
    options = (
        "ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = "
        f"{style.charset} COLLATE = {style.collate} COMMENT = '{escape_sql_string(table_comment)}'"
    )
    reviews = [c.review for c in columns if c.review]
    return TableSchema(
        name=do_table.name,
        columns=columns,
        indexes=[IndexDef("PRIMARY", ["id"], True, "primary", "PRIMARY KEY (`id`) USING BTREE")],
        comment=table_comment,
        options_tail=options,
        origin="code_do",
        review=reviews,
    )


# ---------------------------------------------------------------------------
# 差异计算
# ---------------------------------------------------------------------------


def compare_columns(old: TableSchema, new: TableSchema, origin: str) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    old_cols = {c.name.lower(): c for c in old.columns}
    new_cols = {c.name.lower(): c for c in new.columns}
    for name, col in new_cols.items():
        if name not in old_cols:
            changes.append({"action": "add_column", "column": col.name, "definition": col.definition, "origin": origin})
        elif old_cols[name].signature() != col.signature():
            changes.append(
                {
                    "action": "modify_column",
                    "column": col.name,
                    "before": old_cols[name].definition,
                    "after": col.definition,
                    "origin": origin,
                }
            )
    for name, col in old_cols.items():
        if name not in new_cols:
            changes.append(
                {
                    "action": "drop_column",
                    "column": col.name,
                    "before": col.definition,
                    "origin": origin,
                }
            )
    return changes


def compare_indexes(old: TableSchema, new: TableSchema) -> list[dict[str, Any]]:
    old_idx = {i.name.lower(): i for i in old.indexes}
    new_idx = {i.name.lower(): i for i in new.indexes}
    changes: list[dict[str, Any]] = []
    for name, idx in new_idx.items():
        if name not in old_idx:
            changes.append({"action": "add_index", "index": idx.name, "definition": idx.definition})
        elif old_idx[name].signature() != idx.signature():
            changes.append(
                {
                    "action": "modify_index",
                    "index": idx.name,
                    "before": old_idx[name].definition,
                    "after": idx.definition,
                }
            )
    for name, idx in old_idx.items():
        if name not in new_idx:
            changes.append({"action": "drop_index", "index": idx.name, "before": idx.definition})
    return changes


def preserve_auto_increment(local_options: str, new_options: str) -> str:
    """替换表结构时保留更大的本地 AUTO_INCREMENT，避免后续插入主键冲突。"""
    local_m = re.search(r"AUTO_INCREMENT\s*=\s*(\d+)", local_options or "", re.I)
    new_m = re.search(r"AUTO_INCREMENT\s*=\s*(\d+)", new_options or "", re.I)
    if not local_m:
        return new_options
    local_value = int(local_m.group(1))
    if new_m:
        if local_value <= int(new_m.group(1)):
            return new_options
        return re.sub(r"AUTO_INCREMENT\s*=\s*\d+", f"AUTO_INCREMENT = {local_value}", new_options, count=1, flags=re.I)
    if re.search(r"ENGINE\s*=\s*InnoDB", new_options, re.I):
        return re.sub(r"ENGINE\s*=\s*InnoDB", f"ENGINE = InnoDB AUTO_INCREMENT = {local_value}", new_options, count=1, flags=re.I)
    return new_options


def merge_upstream_table(old: TableSchema, new: TableSchema, local: TableSchema) -> TableSchema:
    """三方合并：以新上游为准，保留本地独有的列和索引。"""
    old_names = {c.name.lower() for c in old.columns}
    new_names = {c.name.lower() for c in new.columns}
    local_only_cols = [c for c in local.columns if c.name.lower() not in old_names and c.name.lower() not in new_names]
    merged = TableSchema(
        name=new.name,
        columns=list(new.columns),
        indexes=list(new.indexes),
        comment=new.comment,
        options_tail=new.options_tail,
        origin="upstream_sql",
    )
    base_index = next((i for i, c in enumerate(merged.columns) if c.name.lower() in BASE_FIELD_NAMES), len(merged.columns))
    for col in local_only_cols:
        merged.columns.insert(base_index, col)
        base_index += 1
    old_idx_names = {i.name.lower() for i in old.indexes}
    new_idx_names = {i.name.lower() for i in new.indexes}
    for idx in local.indexes:
        if idx.name.lower() not in old_idx_names and idx.name.lower() not in new_idx_names:
            merged.indexes.append(idx)
    return merged


def diff_sql_docs(old_doc: Optional[SqlDocument], new_doc: Optional[SqlDocument], local_tables: dict[str, tuple[str, TableSchema]]) -> list[Change]:
    changes: list[Change] = []
    old_tables = old_doc.tables if old_doc else {}
    new_tables = new_doc.tables if new_doc else {}
    for name in sorted(new_tables):
        new = new_tables[name]
        old = old_tables.get(name)
        local_entry = local_tables.get(name)
        local = local_entry[1] if local_entry else None
        if old is None and local is None:
            changes.append(Change("create_table", name, "upstream_sql", new_table=new, new_inserts=list(new.inserts)))
        elif old is None:
            # 本地已有该表、但旧上游没有：按上游新版本合并，保留本地独有列
            if local is not None and local.signature_hash() != new.signature_hash():
                empty = TableSchema(name=name)
                target = merge_upstream_table(empty, new, local)
                change = Change("alter_table", name, "upstream_sql", new_table=target, new_inserts=list(new.inserts))
                change.column_changes = compare_columns(local, target, "upstream_sql")
                change.index_changes = compare_indexes(local, target)
                changes.append(change)
        elif old is not None and old.signature() != new.signature():
            target = merge_upstream_table(old, new, local) if local else new
            change = Change("alter_table", name, "upstream_sql", new_table=target, new_inserts=list(new.inserts))
            change.column_changes = compare_columns(local or old, target, "upstream_sql") if local else compare_columns(old, new, "upstream_sql")
            change.index_changes = compare_indexes(local or old, target) if local else compare_indexes(old, new)
            changes.append(change)
        elif old is not None and local is not None and local.signature_hash() != new.signature_hash():
            # 上游没变、本地与上游不同：不自动覆盖，只提示
            pass
    for name in sorted(set(old_tables) - set(new_tables)):
        if name in local_tables:
            changes.append(Change("drop_table", name, "upstream_sql", old_table=old_tables[name], needs_review=["上游已删除此表，确认后才能删除"]))
    if old_doc and new_doc:
        for name in sorted(set(old_tables) & set(new_tables)):
            old_ins = set(normalize_space(x) for x in old_tables[name].inserts)
            new_ins = set(normalize_space(x) for x in new_tables[name].inserts)
            if old_ins != new_ins and name in local_tables:
                added = len(new_ins - old_ins)
                removed = len(old_ins - new_ins)
                if added or removed:
                    changes.append(
                        Change(
                            "data",
                            name,
                            "upstream_sql",
                            data_added=added,
                            data_removed=removed,
                            note="初始化数据差异，需 --include-data 才会写入",
                        )
                    )
        old_routines = old_doc.routines
        new_routines = new_doc.routines
        for key, routine in sorted(new_routines.items()):
            old = old_routines.get(key)
            if old is None:
                changes.append(Change("create_routine", routine.name, "upstream_sql", routine=routine))
            elif old.signature() != routine.signature():
                changes.append(Change("alter_routine", routine.name, "upstream_sql", routine=routine, old_routine=old))
        for key, routine in sorted(old_routines.items()):
            if key not in new_routines:
                changes.append(
                    Change(
                        "drop_routine",
                        routine.name,
                        "upstream_sql",
                        old_routine=routine,
                        needs_review=["上游已删除该例程，确认后才能删除"],
                    )
                )
    return changes


def diff_do_tables(
    old_tables: dict[str, DoTable],
    new_tables: dict[str, DoTable],
    style_provider,
    covered: set[str],
) -> list[Change]:
    changes: list[Change] = []
    for name in sorted(new_tables):
        if name in covered:
            continue
        new_do = new_tables[name]
        old_do = old_tables.get(name)
        style = style_provider(new_do)
        new_schema = derive_table(new_do, style)
        if old_do is None:
            change = Change("create_table", name, "code_do", new_table=new_schema, needs_review=list(new_schema.review))
            if [i.kind for i in new_schema.indexes] in ([], ["primary"]):
                change.needs_review.append("索引仅包含主键，需按上游 SQL 或实际查询补充")
            changes.append(change)
            continue
        old_schema = derive_table(old_do, style)
        col_changes = []
        old_cols = {c.name.lower(): c for c in old_schema.columns}
        new_cols = {c.name.lower(): c for c in new_schema.columns}
        for col_name, col in new_cols.items():
            if col_name not in old_cols:
                col_changes.append({"action": "add_column", "column": col.name, "definition": col.definition, "origin": "code_do", "review": col.review})
            elif old_cols[col_name].signature() != col.signature():
                col_changes.append(
                    {
                        "action": "modify_column",
                        "column": col.name,
                        "before": old_cols[col_name].definition,
                        "after": col.definition,
                        "origin": "code_do",
                        "review": col.review,
                    }
                )
        for col_name, col in old_cols.items():
            if col_name not in new_cols:
                col_changes.append({"action": "drop_column", "column": col.name, "before": col.definition, "origin": "code_do", "needs_review": True})
        if col_changes:
            change = Change("alter_columns", name, "code_do", new_table=new_schema, column_changes=col_changes)
            change.needs_review = [c.get("review") for c in col_changes if c.get("review")]
            changes.append(change)
    for name in sorted(set(old_tables) - set(new_tables)):
        if name in covered:
            continue
        changes.append(Change("drop_table", name, "code_do", old_table=derive_table(old_tables[name], style_provider(old_tables[name])), needs_review=["代码中已无对应 DO，确认后才能删除"]))
    return changes


# ---------------------------------------------------------------------------
# 渲染与写入
# ---------------------------------------------------------------------------


def render_structure_block(table: TableSchema, newline: str = "\n") -> str:
    defs = [f"  {c.definition}" for c in table.columns]
    defs += [f"  {i.definition}" for i in table.indexes]
    body = ",\n".join(defs)
    options = table.options_tail or (
        f"ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '{escape_sql_string(table.comment)}'"
    )
    text = (
        f"-- ----------------------------{newline}"
        f"-- Table structure for {table.name}{newline}"
        f"-- ----------------------------{newline}"
        f"DROP TABLE IF EXISTS `{table.name}`;{newline}"
        f"CREATE TABLE `{table.name}`  ({newline}"
        f"{body}{newline}"
        f") {options};{newline}"
    )
    return text


def render_records_block(name: str, inserts: list[str], newline: str = "\n") -> str:
    lines = [
        f"-- ----------------------------{newline}",
        f"-- Records of {name}{newline}",
        f"-- ----------------------------{newline}",
        f"BEGIN;{newline}",
    ]
    for stmt in inserts:
        stmt = stmt.rstrip()
        if not stmt.endswith(";"):
            stmt += ";"
        lines.append(stmt + newline)
    lines.append(f"COMMIT;{newline}")
    return "".join(lines)


def definition_lines(table: TableSchema, newline: str) -> list[str]:
    definitions = [c.definition for c in table.columns] + [i.definition for i in table.indexes]
    lines: list[str] = []
    for index, definition in enumerate(definitions):
        suffix = "," if index < len(definitions) - 1 else ""
        lines.append(f"  {definition}{suffix}" + newline)
    return lines


def find_insertion_point(doc: SqlDocument, table_name: str) -> int:
    names = sorted(doc.tables)
    for name in names:
        if name.lower() > table_name.lower():
            return doc.tables[name].header_start
    if doc.tail_start >= 0:
        return doc.tail_start
    return len(doc.lines)


def locate_tail(doc: SqlDocument) -> int:
    for i, line in enumerate(doc.lines):
        if line.strip().upper().startswith("SET FOREIGN_KEY_CHECKS = 1"):
            return i
    return len(doc.lines)


def routine_block(routine: Routine, newline: str) -> str:
    raw = routine.raw.rstrip() + newline
    if "DELIMITER" not in raw.upper():
        raw = f"DELIMITER ;;{newline}" + raw
        if not raw.rstrip().endswith(";"):
            raw = raw.rstrip() + f";;{newline}"
        raw += f"DELIMITER ;{newline}"
    elif not re.search(r"DELIMITER\s+;\s*$", raw, re.I):
        raw += f"DELIMITER ;{newline}"
    return raw


def apply_create_routine(doc: SqlDocument, routine: Routine) -> None:
    block = routine_block(routine, doc.newline)
    pos = doc.tail_start if doc.tail_start >= 0 else locate_tail(doc)
    insertion = doc.newline + block + doc.newline
    doc.lines[pos:pos] = insertion.splitlines(keepends=True)
    refreshed = parse_sql_text(doc.render(), doc.path, readonly=doc.readonly)
    doc.tables, doc.routines = refreshed.tables, refreshed.routines


def apply_alter_routine(doc: SqlDocument, local: Routine, new: Routine) -> None:
    block = routine_block(new, doc.newline)
    doc.lines[local.start : local.end + 1] = block.splitlines(keepends=True)
    refreshed = parse_sql_text(doc.render(), doc.path, readonly=doc.readonly)
    doc.tables, doc.routines = refreshed.tables, refreshed.routines


def apply_drop_routine(doc: SqlDocument, local: Routine) -> None:
    del doc.lines[local.start : local.end + 1]
    refreshed = parse_sql_text(doc.render(), doc.path, readonly=doc.readonly)
    doc.tables, doc.routines = refreshed.tables, refreshed.routines


def rewrite_insert_line(line: str, valid_columns: set[str]) -> Optional[str]:
    table, cols, tuples = parse_insert_columns(line)
    if not table or not cols:
        return line
    keep = [i for i, c in enumerate(cols) if c.lower() in valid_columns]
    if len(keep) == len(cols):
        return line
    if not keep:
        return None
    new_cols = ", ".join(f"`{cols[i]}`" for i in keep)
    new_tuples: list[str] = []
    for tup in tuples:
        inner = tup.strip()
        if inner.startswith("(") and inner.endswith(")"):
            inner = inner[1:-1]
        parts = split_top_level(inner)
        values = [inner[s:e].strip() for s, e in parts]
        if len(values) != len(cols):
            return line  # 结构异常时交给校验报错，不擅自改写
        new_tuples.append("(" + ", ".join(values[i] for i in keep) + ")")
    return f"INSERT INTO `{table}` ({new_cols}) VALUES " + ", ".join(new_tuples) + ";"


def rewrite_table_inserts(doc: SqlDocument, table_name: str) -> None:
    table = doc.tables.get(table_name)
    if not table or table.records_start < 0:
        return
    valid = {c.name.lower() for c in table.columns}
    start, end = table.records_start, table.records_end
    replacements: list[tuple[int, Optional[str]]] = []
    for index in range(start, min(end + 1, len(doc.lines))):
        line = doc.lines[index]
        if re.match(r"^INSERT INTO\s+`" + re.escape(table_name) + r"`", line, re.I):
            replacements.append((index, rewrite_insert_line(line, valid)))
    for index, new_line in reversed(replacements):
        if new_line is None:
            del doc.lines[index]
        else:
            doc.lines[index] = new_line.rstrip() + doc.newline
    if replacements:
        refreshed = parse_sql_text(doc.render(), doc.path, readonly=doc.readonly)
        doc.tables, doc.routines = refreshed.tables, refreshed.routines


def apply_create_table(doc: SqlDocument, table: TableSchema, inserts: Optional[list[str]] = None) -> None:
    nl = doc.newline
    block = (
        render_structure_block(table, nl)
        + nl
        + render_records_block(table.name, inserts or [], nl)
        + nl
    )
    pos = find_insertion_point(doc, table.name)
    if pos > 0 and doc.lines[pos - 1].strip():
        block = nl + block
    doc.lines[pos:pos] = block.splitlines(keepends=True)
    refreshed = parse_sql_text(doc.render(), doc.path, readonly=doc.readonly)
    doc.tables = refreshed.tables


def apply_alter_columns(doc: SqlDocument, table: TableSchema, changes: list[dict[str, Any]]) -> None:
    if not changes:
        return
    # 直接按修改后的模型重建列定义区，未变更列使用原始 definition，保持逐字节一致
    start = table.create_start + 1
    end = table.create_end
    new_lines = definition_lines(table, doc.newline)
    doc.lines[start:end] = new_lines


def apply_replace_table(doc: SqlDocument, table: TableSchema, include_data: bool, upstream_inserts: Optional[list[str]]) -> None:
    start = table.header_start
    end = table.create_end + 1
    new_block = render_structure_block(table, doc.newline).splitlines(keepends=True)
    doc.lines[start:end] = new_block
    # 重新定位 records
    doc2 = parse_sql_text(doc.render(), doc.path, readonly=doc.readonly)
    doc.tables = doc2.tables
    refreshed = doc.tables.get(table.name)
    if include_data and upstream_inserts is not None and refreshed and refreshed.records_start >= 0:
        insert_pos = refreshed.records_end
        existing = {normalize_space(x) for x in refreshed.inserts}
        new_lines = []
        for stmt in upstream_inserts:
            if normalize_space(stmt) in existing:
                continue
            stmt = stmt.rstrip()
            if not stmt.endswith(";"):
                stmt += ";"
            new_lines.append(stmt + doc.newline)
        doc.lines[insert_pos:insert_pos] = new_lines
        refreshed = parse_sql_text(doc.render(), doc.path, readonly=doc.readonly).tables.get(table.name)
        if refreshed:
            doc.tables = parse_sql_text(doc.render(), doc.path, readonly=doc.readonly).tables


def update_header_date(doc: SqlDocument) -> None:
    dt = now_local()
    stamp = dt.strftime("%d/%m/%Y %H:%M:%S")
    for i, line in enumerate(doc.lines):
        if re.match(r"^ Date:\s*", line):
            doc.lines[i] = f" Date: {stamp}\n" if doc.newline == "\n" else f" Date: {stamp}\r\n"
            return


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------


def split_value_tuples(values_text: str) -> list[str]:
    text = values_text.strip()
    if text.endswith(";"):
        text = text[:-1]
    if not text.startswith("("):
        return []
    spans = split_top_level(text)
    return [text[s:e].strip() for s, e in spans]


def parse_insert_columns(line: str) -> tuple[str, list[str], list[str]]:
    m = re.match(r"INSERT INTO\s+`([^`]+)`\s*\(([^)]*)\)\s*VALUES\s*(.*)$", line, re.I | re.S)
    if not m:
        return "", [], []
    table = m.group(1)
    cols = re.findall(r"`([^`]+)`", m.group(2))
    tuples = split_value_tuples(m.group(3))
    return table, cols, tuples


def count_tuple_values(tuple_text: str) -> int:
    inner = tuple_text.strip()
    if inner.startswith("("):
        inner = inner[1:]
    if inner.endswith(")"):
        inner = inner[:-1]
    if not inner.strip():
        return 0
    return len(split_top_level(inner))


def validate_document(doc: SqlDocument) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    # 重新解析
    try:
        reparsed = parse_sql_text(doc.render(), doc.path, readonly=doc.readonly)
    except Exception as exc:  # noqa: BLE001
        return [{"level": "error", "message": f"重新解析失败: {exc}"}]
    if len(reparsed.tables) != len(doc.tables):
        errors.append({"level": "error", "message": f"表数量不一致: 修改后 {len(doc.tables)}，重新解析 {len(reparsed.tables)}"})
    if len(reparsed.routines) != len(doc.routines):
        errors.append(
            {"level": "error", "message": f"例程数量不一致: 修改后 {len(doc.routines)}，重新解析 {len(reparsed.routines)}"}
        )
    if _sqlglot is not None and not reparsed.routines:
        try:
            _sqlglot.parse(doc.render(), read="mysql")
        except Exception as exc:  # noqa: BLE001
            errors.append({"level": "error", "message": f"sqlglot 语法校验失败: {exc}"})
    for name, routine in reparsed.routines.items():
        upper = routine.raw.upper()
        if "DELIMITER" in upper:
            open_count = len(re.findall(r"DELIMITER\s+\S+", upper))
            close_count = len(re.findall(r"DELIMITER\s+;", upper))
            if not open_count or not close_count:
                errors.append({"level": "error", "message": f"例程 {name} 的 DELIMITER 不完整"})
    for name, table in reparsed.tables.items():
        col_names = [c.name.lower() for c in table.columns]
        dup = {x for x in col_names if col_names.count(x) > 1}
        if dup:
            errors.append({"level": "error", "message": f"表 {name} 存在重复列: {sorted(dup)}"})
        if not table.pk():
            errors.append({"level": "warning", "message": f"表 {name} 没有主键"})
        for idx in table.indexes:
            missing = [c for c in idx.columns if c.lower() not in col_names and idx.kind != "constraint"]
            if missing:
                errors.append({"level": "error", "message": f"表 {name} 的索引 {idx.name} 引用了不存在的列: {missing}"})
        for ins in table.inserts:
            tname, cols, tuples = parse_insert_columns(ins)
            if tname != name:
                continue
            if not cols:
                continue
            missing_cols = [c for c in cols if c.lower() not in col_names]
            if missing_cols:
                errors.append({"level": "error", "message": f"表 {name} 的 INSERT 引用了不存在的列: {missing_cols}"})
            for tup in tuples:
                if count_tuple_values(tup) != len(cols):
                    errors.append(
                        {
                            "level": "error",
                            "message": f"表 {name} 的 INSERT 值个数({count_tuple_values(tup)})与列数({len(cols)})不一致",
                        }
                    )
                    break
    return errors


def validate_before_write(original_docs: dict[str, SqlDocument], edited_docs: dict[str, SqlDocument]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for rel, doc in edited_docs.items():
        if rel not in original_docs:
            errors.append({"level": "error", "message": f"未知文件 {rel}"})
            continue
        if doc.readonly and doc.render() != original_docs[rel].text:
            errors.append({"level": "error", "message": f"只读文件被修改: {rel}"})
        if doc.bom != original_docs[rel].bom:
            errors.append({"level": "error", "message": f"BOM 被改变: {rel}"})
        for item in validate_document(doc):
            errors.append({"level": item["level"], "message": f"{rel}: {item['message']}"})
    return errors


def mysql_validate_docs(edited_docs: dict[str, SqlDocument]) -> dict[str, Any]:
    """可选：把改动后的脚本导入临时 MySQL 库，验证真实语法。"""
    cmd = os.environ.get("SQLSYNC_MYSQL_CMD", "").strip()
    if not cmd:
        return {"status": "skipped", "reason": "未设置 SQLSYNC_MYSQL_CMD"}
    parts = shlex.split(cmd)
    if not parts or shutil.which(parts[0]) is None:
        return {"status": "skipped", "reason": f"找不到 mysql 客户端: {parts[0] if parts else cmd}"}
    results: list[dict[str, Any]] = []
    for index, (rel, doc) in enumerate(sorted(edited_docs.items())):
        if doc.readonly:
            continue
        db_name = f"sqlsync_validate_{os.getpid()}_{index}"
        errors: list[str] = []
        tmp_path = None
        try:
            subprocess.run(
                parts + ["-e", f"DROP DATABASE IF EXISTS `{db_name}`; CREATE DATABASE `{db_name}` DEFAULT CHARACTER SET utf8mb4;"],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".sql", delete=False, newline="") as fh:
                fh.write(doc.render())
                tmp_path = fh.name
            with open(tmp_path, "rb") as fh:
                proc = subprocess.run(parts + [db_name], stdin=fh, capture_output=True, text=True, timeout=300, check=False)
            if proc.returncode != 0:
                errors.append((proc.stderr or proc.stdout or "").strip()[:2000])
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            subprocess.run(parts + ["-e", f"DROP DATABASE IF EXISTS `{db_name}`;"], capture_output=True, text=True, timeout=60, check=False)
        results.append({"file": rel, "database": db_name, "status": "failed" if errors else "passed", "errors": errors})
    if any(item["status"] == "failed" for item in results):
        return {"status": "failed", "results": results}
    return {"status": "passed", "results": results}


# ---------------------------------------------------------------------------
# 映射配置与审计
# ---------------------------------------------------------------------------


class Mapping:
    def __init__(self, data: dict[str, Any], path: Path):
        self.data = data
        self.path = path

    @classmethod
    def load(cls, path: Path = DEFAULT_MAPPING) -> "Mapping":
        return cls(json.loads(path.read_text(encoding="utf-8")), path)

    def save(self) -> None:
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    @property
    def sql_root(self) -> str:
        return self.data.get("sql_root", "sql/mysql")

    @property
    def readonly_files(self) -> list[str]:
        return self.data.get("readonly_files", [])

    @property
    def skip_tables(self) -> set[str]:
        return set(self.data.get("skip_tables", []))

    @property
    def explicit_tables(self) -> dict[str, str]:
        return self.data.get("explicit_tables", {})

    @property
    def modules(self) -> dict[str, dict[str, Any]]:
        return self.data.get("modules", {})

    def target_file_for(self, table_name: str, module: Optional[str], local_tables: dict[str, tuple[str, TableSchema]]) -> Optional[str]:
        if table_name in local_tables:
            return local_tables[table_name][0]
        explicit = self.explicit_tables.get(table_name)
        if explicit:
            return explicit
        if module:
            mod = self.modules.get(module)
            if mod:
                candidates = [f for f in mod.get("files", []) if f not in self.readonly_files]
                if candidates:
                    return candidates[0]
        # 按表名前缀寻找已有归属
        prefix = table_name.split("_", 1)[0]
        same_prefix: dict[str, int] = {}
        for rel, (frel, table) in local_tables.items():
            if table.name.split("_", 1)[0] == prefix:
                same_prefix[frel] = same_prefix.get(frel, 0) + 1
        if len(same_prefix) == 1:
            return next(iter(same_prefix))
        return None

    def baseline_for(self, rel: str) -> dict[str, Any]:
        files = self.data.setdefault("files", {})
        return files.setdefault(rel, {"last_synced_version": None, "schema_fingerprint": None, "tables": {}})

    def update_baseline(self, rel: str, version: Optional[str], doc: SqlDocument) -> None:
        entry = self.baseline_for(rel)
        entry["last_synced_version"] = version or entry.get("last_synced_version")
        entry["schema_fingerprint"] = sha256_json({name: t.signature_hash() for name, t in sorted(doc.tables.items())})
        entry["tables"] = {name: t.signature_hash() for name, t in sorted(doc.tables.items())}
        entry["updated_at"] = timestamp_iso()


def write_audit(payload: dict[str, Any]) -> Path:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    path = AUDIT_DIR / f"sync-{payload['sync_id']}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_last_audit() -> Optional[dict[str, Any]]:
    if not AUDIT_DIR.exists():
        return None
    files = sorted(AUDIT_DIR.glob("sync-*.json"))
    if not files:
        return None
    try:
        return json.loads(files[-1].read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# 源码包解析与命令实现
# ---------------------------------------------------------------------------


def find_source_sql(root: Path) -> list[Path]:
    base = root / "sql" if (root / "sql").is_dir() else root
    return sorted(base.rglob("*.sql"))


def load_source_sql_tables(root: Path) -> dict[str, TableSchema]:
    result: dict[str, TableSchema] = {}
    for path in find_source_sql(root):
        try:
            doc = load_sql_document(path)
        except UnicodeDecodeError:
            continue
        for name, table in doc.tables.items():
            if name in result:
                print(f"[warn] 上游 SQL 中表 {name} 重复出现，保留 {result[name].source_file}", file=sys.stderr)
                continue
            table.source_file = path.as_posix()
            result[name] = table
    return result


def style_for_module(module: Optional[str], mapping: Mapping, local_docs: dict[str, SqlDocument]) -> StyleContext:
    if module and module in mapping.modules:
        files = mapping.modules[module].get("files", [])
        for rel in files:
            if rel in local_docs:
                return StyleContext.from_tables(local_docs[rel].tables.values())
    tables: list[TableSchema] = []
    for doc in local_docs.values():
        if not doc.readonly:
            tables.extend(doc.tables.values())
    return StyleContext.from_tables(tables)


def style_provider_factory(mapping: Mapping, local_docs: dict[str, SqlDocument]):
    cache: dict[str, StyleContext] = {}

    def provider(do_table: DoTable) -> StyleContext:
        key = do_table.module
        if key not in cache:
            cache[key] = style_for_module(key, mapping, local_docs)
        return cache[key]

    return provider


def find_do_module_for_table(table_name: str, do_tables: dict[str, DoTable]) -> Optional[str]:
    do = do_tables.get(table_name)
    return do.module if do else None


MAPPER_TABLE_RE = re.compile(
    r"\b(?:FROM|JOIN|UPDATE|INSERT\s+INTO|DELETE\s+FROM|TRUNCATE\s+TABLE)\s+`?([A-Za-z0-9_]+)`?",
    re.I,
)
SQL_WORDS = {
    "select",
    "where",
    "set",
    "values",
    "dual",
    "on",
    "as",
    "left",
    "right",
    "inner",
    "outer",
    "join",
    "group",
    "order",
    "limit",
    "union",
}


def load_mapper_usage(root: Path) -> dict[str, list[str]]:
    """返回 表名 -> 引用它的 Mapper XML 文件列表。"""
    result: dict[str, list[str]] = {}
    for path in sorted(root.rglob("*.xml")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "<mapper" not in text:
            continue
        tables = set()
        for m in MAPPER_TABLE_RE.finditer(text):
            name = m.group(1)
            if name.lower() not in SQL_WORDS:
                tables.add(name)
        if not tables:
            continue
        rel = path.as_posix()
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            pass
        for table in tables:
            result.setdefault(table, []).append(rel)
    return result


def load_mapper_fingerprints(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(root.rglob("*.xml")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "<mapper" not in text:
            continue
        rel = path.as_posix()
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            pass
        result[rel] = sha256_text(text)
    return result


def mapper_review(old_dir: Path, new_dir: Path, covered: set[str]) -> list[dict[str, str]]:
    old_usage = load_mapper_usage(old_dir)
    new_usage = load_mapper_usage(new_dir)
    old_hash = load_mapper_fingerprints(old_dir)
    new_hash = load_mapper_fingerprints(new_dir)
    changed_files = {rel for rel in set(old_hash) | set(new_hash) if old_hash.get(rel) != new_hash.get(rel)}
    if not changed_files:
        return []
    tables: set[str] = set()
    for table, files in {**old_usage, **new_usage}.items():
        if set(files) & changed_files:
            tables.add(table)
    results: list[dict[str, str]] = []
    for table in sorted(tables):
        if table in covered:
            continue
        results.append(
            {
                "table": table,
                "files": ", ".join(sorted(changed_files)),
                "reason": "Mapper XML 发生变更，请检查是否涉及索引、约束或字段调整",
            }
        )
    return results


def resolve_routine_target(
    change: Change,
    mapping: Mapping,
    local_docs: dict[str, SqlDocument],
    local_tables: dict[str, tuple[str, TableSchema]],
) -> Optional[str]:
    key = change.table.lower()
    for rel, doc in local_docs.items():
        if key in doc.routines:
            return rel
    raw = (change.routine or change.old_routine).raw if (change.routine or change.old_routine) else ""
    counts: dict[str, int] = {}
    for table_name, (rel, _table) in local_tables.items():
        if re.search(r"\b" + re.escape(table_name) + r"\b", raw, re.I):
            counts[rel] = counts.get(rel, 0) + 1
    candidates = [
        (count, rel)
        for rel, count in counts.items()
        if rel not in mapping.readonly_files and rel in local_docs
    ]
    if candidates:
        candidates.sort(reverse=True)
        return candidates[0][1]
    explicit = mapping.data.get("explicit_routines", {}).get(change.table)
    return explicit


def types_compatible(a: str, b: str) -> bool:
    if a == b:
        return True
    strings = {"string", "text", "json"}
    numbers = {"int", "bool"}
    dates = {"datetime", "date", "time"}
    decimals = {"decimal", "float"}
    if a in strings and b in strings:
        return True
    if a in numbers and b in numbers:
        return True
    if a in dates and b in dates:
        return True
    if a in decimals and b in decimals:
        return True
    return False


def cmd_baseline(args: argparse.Namespace, mapping: Mapping, local_docs: dict[str, SqlDocument]) -> int:
    version = args.version or project_version()
    count = 0
    tables = 0
    for rel, doc in sorted(local_docs.items()):
        if doc.readonly:
            continue
        mapping.update_baseline(rel, version, doc)
        count += 1
        tables += len(doc.tables)
    if args.write:
        if version:
            mapping.data["last_synced_version"] = version
        mapping.save()
    print(f"基线（{'已写入' if args.write else '预演'}）：{count} 个脚本，{tables} 张表，版本 {version}")
    return 0


def cmd_check(args: argparse.Namespace, mapping: Mapping, local_docs: dict[str, SqlDocument]) -> int:
    local_tables = index_local_tables(local_docs)
    do_tables = load_do_tables(REPO_ROOT)
    skip = mapping.skip_tables
    missing_tables: list[dict[str, str]] = []
    missing_columns: list[dict[str, Any]] = []
    type_mismatch: list[dict[str, Any]] = []
    type_warnings: list[dict[str, Any]] = []
    extra_columns: list[dict[str, Any]] = []
    orphan_tables: list[dict[str, str]] = []
    for name, do in sorted(do_tables.items()):
        if name in skip:
            continue
        entry = local_tables.get(name)
        if not entry:
            missing_tables.append({"table": name, "module": do.module, "do": do.source_file})
            continue
        rel, table = entry
        style = style_for_module(do.module, mapping, local_docs)
        derived = derive_table(do, style)
        sql_cols = {c.name.lower(): c for c in table.columns}
        for col in derived.columns:
            existing = sql_cols.get(col.name.lower())
            if not existing:
                missing_columns.append({"table": name, "column": col.name, "definition": col.definition, "file": rel})
            elif not types_compatible(existing.category(), col.category()):
                type_mismatch.append(
                    {
                        "table": name,
                        "column": col.name,
                        "sql": existing.type,
                        "code": col.type,
                        "file": rel,
                    }
                )
            elif normalize_type(existing.type) != normalize_type(col.type) and col.category() in ("datetime", "decimal", "float"):
                type_warnings.append(
                    {
                        "table": name,
                        "column": col.name,
                        "sql": existing.type,
                        "code": col.type,
                        "file": rel,
                    }
                )
        do_cols = {c.name.lower() for c in derived.columns}
        for col in table.columns:
            if col.name.lower() not in do_cols and col.name.lower() not in BASE_FIELD_NAMES:
                extra_columns.append({"table": name, "column": col.name, "definition": col.definition, "file": rel})
    for name, (rel, table) in sorted(local_tables.items()):
        if name in do_tables or name in skip:
            continue
        if local_docs.get(rel) and local_docs[rel].readonly:
            continue
        orphan_tables.append({"table": name, "file": rel})
    report = {
        "missing_tables": missing_tables,
        "missing_columns": missing_columns,
        "type_mismatch": type_mismatch,
        "type_warnings": type_warnings,
        "extra_columns": extra_columns,
        "orphan_tables": orphan_tables,
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"代码 DO 表: {len(do_tables)}；脚本中可写表: {sum(1 for n, (r, _) in local_tables.items() if not local_docs[r].readonly)}")
        print(f"\n[缺失表] {len(missing_tables)}")
        for item in missing_tables:
            print(f"  - {item['table']}  (模块 {item['module']}, {item['do']})")
        print(f"\n[缺失字段] {len(missing_columns)}")
        for item in missing_columns:
            print(f"  - {item['table']}.{item['column']}  -> {item['file']}")
        print(f"\n[类型不一致] {len(type_mismatch)}")
        for item in type_mismatch:
            print(f"  - {item['table']}.{item['column']}: SQL={item['sql']}  Code={item['code']}")
        print(f"\n[类型差异提示] {len(type_warnings)}")
        for item in type_warnings:
            print(f"  - {item['table']}.{item['column']}: SQL={item['sql']}  Code={item['code']}")
        print(f"\n[脚本多出的字段] {len(extra_columns)}")
        for item in extra_columns:
            print(f"  - {item['table']}.{item['column']}  ({item['file']})")
        print(f"\n[无 DO 的表] {len(orphan_tables)}")
        for item in orphan_tables:
            print(f"  - {item['table']}  ({item['file']})")
    return 0 if not (missing_tables or missing_columns or type_mismatch) else 1


def cmd_diff(args: argparse.Namespace, mapping: Mapping, local_docs: dict[str, SqlDocument]) -> int:
    old_dir = Path(args.old_dir).resolve()
    new_dir = Path(args.new_dir).resolve() if args.new_dir else REPO_ROOT
    if not old_dir.is_dir():
        print(f"[error] 旧源码目录不存在: {old_dir}", file=sys.stderr)
        return 2
    if not new_dir.is_dir():
        print(f"[error] 新源码目录不存在: {new_dir}", file=sys.stderr)
        return 2
    local_tables = index_local_tables(local_docs)
    old_doc_sql = load_source_sql_tables(old_dir)
    new_doc_sql = load_source_sql_tables(new_dir)
    sql_changes = diff_sql_docs(
        SqlDocument(old_dir / "sql", "", tables=old_doc_sql),
        SqlDocument(new_dir / "sql", "", tables=new_doc_sql),
        local_tables,
    )
    covered = {c.table for c in sql_changes if c.action in ("create_table", "alter_table", "alter_columns")}
    old_do = load_do_tables(old_dir)
    new_do = load_do_tables(new_dir)
    provider = style_provider_factory(mapping, local_docs)
    do_changes = diff_do_tables(old_do, new_do, provider, covered)
    changes = [c for c in sql_changes if c.action != "data"] + do_changes
    data_changes = [c for c in sql_changes if c.action == "data"]
    mapper_items = mapper_review(old_dir, new_dir, covered)
    current_do = load_do_tables(REPO_ROOT)
    for change in changes + data_changes:
        if change.action in ("create_routine", "alter_routine", "drop_routine"):
            change.target_file = resolve_routine_target(change, mapping, local_docs, local_tables)
        else:
            module = find_do_module_for_table(change.table, new_do) or find_do_module_for_table(change.table, current_do)
            change.target_file = mapping.target_file_for(change.table, module, local_tables)
        change.compute_hash()
        local_entry = local_tables.get(change.table)
        if change.action in ("create_table", "alter_table", "alter_columns") and local_entry:
            if change.new_table and local_entry[1].signature_hash() == change.new_table.signature_hash():
                change.status = "already_synced"
            elif change.action == "create_table":
                change.status = "already_exists"
        if change.action in ("create_routine", "alter_routine") and change.target_file:
            local_doc = local_docs.get(change.target_file)
            local_routine = local_doc.routines.get(change.table.lower()) if local_doc else None
            if local_routine and change.routine and local_routine.signature() == change.routine.signature():
                change.status = "already_synced"
    changes, ignored = split_changes_by_writable(changes, mapping)
    data_changes, ignored_data = split_changes_by_writable(data_changes, mapping)
    ignored.extend(ignored_data)
    unmapped = [{"table": c.table, "reason": "找不到已存在的目标 SQL 文件"} for c in changes if not c.target_file]
    payload = {
        "old_dir": old_dir.as_posix(),
        "new_dir": new_dir.as_posix(),
        "version": args.version,
        "changes": [change_to_json(c) for c in changes],
        "data_changes": [change_to_json(c) for c in data_changes],
        "needs_review": [x for c in changes for x in c.needs_review if x],
        "unmapped": unmapped,
        "ignored": ignored,
        "mapper_review": mapper_items,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"对比 {old_dir} -> {new_dir}")
        print(f"变更 {len(changes)} 项：")
        for change in changes:
            target = change.target_file or "（未映射）"
            suffix = f" [已同步]" if change.status == "already_synced" else ""
            print(f"  - [{change.origin}] {change.describe()} -> {target}{suffix}")
            if change.column_changes:
                for item in change.column_changes[:5]:
                    print(f"      {item['action']}: {item.get('column', '')}")
            if change.needs_review:
                for item in change.needs_review:
                    print(f"      ! 待确认: {item}")
        if data_changes:
            print(f"初始化数据差异 {len(data_changes)} 张表（需 --include-data）")
        if unmapped:
            print(f"未映射 {len(unmapped)} 张表：")
            for item in unmapped:
                print(f"  - {item['table']}")
        if ignored:
            print(f"忽略（只读脚本）{len(ignored)} 项：")
            for item in ignored:
                print(f"  - {item['table']}（{item['reason']}）")
        if mapper_items:
            print(f"Mapper XML 变更需人工确认 {len(mapper_items)} 项：")
            for item in mapper_items:
                print(f"  - {item['table']}（{item['files']}）")
    return 0


def change_to_json(change: Change) -> dict[str, Any]:
    return {
        "action": change.action,
        "table": change.table,
        "origin": change.origin,
        "target_file": change.target_file,
        "status": change.status,
        "change_hash": change.change_hash,
        "column_changes": change.column_changes,
        "index_changes": change.index_changes,
        "data_added": change.data_added,
        "data_removed": change.data_removed,
        "new_inserts": len(change.new_inserts),
        "note": change.note,
        "needs_review": [x for x in change.needs_review if x],
        "before": change.old_table.signature() if change.old_table else None,
        "after": change.new_table.signature() if change.new_table else None,
        "routine": {
            "kind": change.routine.kind,
            "name": change.routine.name,
            "signature": change.routine.signature(),
        }
        if change.routine
        else None,
        "old_routine": {
            "kind": change.old_routine.kind,
            "name": change.old_routine.name,
            "signature": change.old_routine.signature(),
        }
        if change.old_routine
        else None,
    }


def split_changes_by_writable(
    changes: list[Change], mapping: Mapping
) -> tuple[list[Change], list[dict[str, str]]]:
    readonly = set(mapping.readonly_files)
    writable: list[Change] = []
    ignored: list[dict[str, str]] = []
    for change in changes:
        if change.target_file and change.target_file in readonly:
            ignored.append({"table": change.table, "reason": f"目标文件只读: {change.target_file}"})
        else:
            writable.append(change)
    return writable, ignored


def apply_changes(
    changes: list[Change],
    mapping: Mapping,
    local_docs: dict[str, SqlDocument],
    upstream_inserts: dict[str, list[str]] | None,
    include_data: bool,
    allow_drop: bool,
) -> tuple[dict[str, SqlDocument], list[dict[str, str]], list[dict[str, Any]]]:
    edited: dict[str, SqlDocument] = {}
    errors: list[dict[str, str]] = []
    applied: list[dict[str, Any]] = []
    local_tables = index_local_tables(local_docs)
    for change in sorted(changes, key=lambda c: (c.target_file or "", c.table)):
        if change.action == "data":
            if not include_data or not change.target_file:
                continue
            rel = change.target_file
            doc = edited.get(rel) or local_docs.get(rel)
            table = doc.tables.get(change.table) if doc else None
            if not doc or not table or table.records_start < 0 or not upstream_inserts:
                continue
            existing = {normalize_space(x) for x in table.inserts}
            added = 0
            insert_pos = table.records_end
            for stmt in upstream_inserts.get(change.table, []):
                if normalize_space(stmt) in existing:
                    continue
                stmt = stmt.rstrip()
                if not stmt.endswith(";"):
                    stmt += ";"
                doc.lines.insert(insert_pos, stmt + doc.newline)
                insert_pos += 1
                added += 1
            if added:
                refreshed = parse_sql_text(doc.render(), doc.path, readonly=doc.readonly)
                doc.tables = refreshed.tables
                edited[rel] = doc
                applied.append({"table": change.table, "status": "data_appended", "file": rel, "rows": added})
            continue
        if not change.target_file:
            errors.append({"level": "error", "message": f"{change.table}: 未找到目标脚本文件"})
            continue
        rel = change.target_file
        doc = edited.get(rel) or local_docs.get(rel)
        if doc is None:
            errors.append({"level": "error", "message": f"{change.table}: 目标文件不存在 {rel}"})
            continue
        if doc.readonly:
            errors.append({"level": "error", "message": f"{change.table}: 目标文件只读 {rel}"})
            continue
        # 当前本地表
        current = doc.tables.get(change.table)
        if change.action in ("create_table", "alter_table", "alter_columns"):
            target_sig = change.new_table.signature_hash() if change.new_table else ""
            if current and current.signature_hash() == target_sig and change.action != "create_table":
                applied.append({"table": change.table, "status": "skipped", "reason": "already_synced"})
                continue
        if change.action == "create_table":
            if current:
                applied.append({"table": change.table, "status": "skipped", "reason": "already_exists"})
                continue
            assert change.new_table is not None
            apply_create_table(doc, change.new_table, change.new_inserts if include_data else [])
            applied.append({"table": change.table, "status": "created", "file": rel})
        elif change.action == "alter_columns":
            if not current:
                errors.append({"level": "error", "message": f"{change.table}: 本地不存在该表，不能做字段变更"})
                continue
            effective: list[dict[str, Any]] = []
            for item in change.column_changes:
                exists = current.column(item.get("column", "")) is not None
                if item["action"] == "add_column" and exists:
                    continue
                if item["action"] in ("modify_column", "drop_column") and not exists:
                    continue
                effective.append(item)
            if not effective:
                applied.append({"table": change.table, "status": "skipped", "reason": "already_synced"})
                continue
            if any(c.get("action") == "drop_column" for c in effective) and not allow_drop:
                applied.append({"table": change.table, "status": "skipped", "reason": "drop_column_requires_allow_drop"})
                continue
            assert change.new_table is not None
            # 以本地表为底，应用新增/修改列
            merged = TableSchema(
                name=current.name,
                columns=list(current.columns),
                indexes=list(current.indexes),
                comment=current.comment,
                options_tail=current.options_tail,
                header_start=current.header_start,
                create_start=current.create_start,
                create_end=current.create_end,
                records_start=current.records_start,
                records_end=current.records_end,
            )
            for item in effective:
                if item["action"] == "add_column":
                    new_col = change.new_table.column(item["column"])
                    if new_col:
                        idx = next((i for i, c in enumerate(merged.columns) if c.name.lower() in BASE_FIELD_NAMES), len(merged.columns))
                        merged.columns.insert(idx, new_col)
                elif item["action"] == "modify_column":
                    new_col = change.new_table.column(item["column"])
                    for i, c in enumerate(merged.columns):
                        if c.name.lower() == item["column"].lower() and new_col:
                            merged.columns[i] = new_col
                elif item["action"] == "drop_column":
                    merged.columns = [c for c in merged.columns if c.name.lower() != item["column"].lower()]
            apply_alter_columns(doc, merged, effective)
            # 更新内存中的表模型
            doc2 = parse_sql_text(doc.render(), doc.path, readonly=doc.readonly)
            doc2.bom, doc2.newline = doc.bom, doc.newline
            doc.tables = doc2.tables
            rewrite_table_inserts(doc, change.table)
            applied.append({"table": change.table, "status": "altered", "file": rel, "columns": effective})
        elif change.action == "alter_table":
            if current is None:
                assert change.new_table is not None
                apply_create_table(doc, change.new_table, change.new_inserts if include_data else [])
                applied.append({"table": change.table, "status": "created", "file": rel})
            else:
                assert change.new_table is not None
                inserts = upstream_inserts.get(change.table) if (include_data and upstream_inserts) else None
                replacement = TableSchema(
                    name=change.new_table.name,
                    columns=list(change.new_table.columns),
                    indexes=list(change.new_table.indexes),
                    comment=change.new_table.comment,
                    options_tail=preserve_auto_increment(current.options_tail, change.new_table.options_tail),
                    header_start=current.header_start,
                    create_start=current.create_start,
                    create_end=current.create_end,
                    records_start=current.records_start,
                    records_end=current.records_end,
                )
                apply_replace_table(doc, replacement, include_data, inserts)
                rewrite_table_inserts(doc, change.table)
                applied.append({"table": change.table, "status": "replaced", "file": rel})
        elif change.action == "drop_table":
            if allow_drop and current:
                start = current.header_start
                end = current.records_end + 1 if current.records_end >= 0 else current.create_end + 1
                del doc.lines[start:end]
                applied.append({"table": change.table, "status": "dropped", "file": rel})
            else:
                applied.append({"table": change.table, "status": "skipped", "reason": "drop_table_requires_allow_drop"})
        elif change.action in ("create_routine", "alter_routine", "drop_routine"):
            local_routine = doc.routines.get(change.table.lower())
            if change.action == "create_routine":
                if local_routine:
                    if change.routine and local_routine.signature() == change.routine.signature():
                        applied.append({"table": change.table, "status": "skipped", "reason": "already_synced"})
                    else:
                        apply_alter_routine(doc, local_routine, change.routine)  # type: ignore[arg-type]
                        applied.append({"table": change.table, "status": "altered", "file": rel})
                    continue
                assert change.routine is not None
                apply_create_routine(doc, change.routine)
                applied.append({"table": change.table, "status": "created", "file": rel})
            elif change.action == "alter_routine":
                assert change.routine is not None
                if local_routine:
                    if local_routine.signature() == change.routine.signature():
                        applied.append({"table": change.table, "status": "skipped", "reason": "already_synced"})
                    else:
                        apply_alter_routine(doc, local_routine, change.routine)
                        applied.append({"table": change.table, "status": "altered", "file": rel})
                else:
                    apply_create_routine(doc, change.routine)
                    applied.append({"table": change.table, "status": "created", "file": rel})
            else:
                if allow_drop and local_routine:
                    apply_drop_routine(doc, local_routine)
                    applied.append({"table": change.table, "status": "dropped", "file": rel})
                else:
                    applied.append({"table": change.table, "status": "skipped", "reason": "drop_routine_requires_allow_drop"})
        if rel not in edited:
            edited[rel] = doc
    return edited, errors, applied


def cmd_sync(args: argparse.Namespace, mapping: Mapping, local_docs: dict[str, SqlDocument]) -> int:
    old_dir = Path(args.old_dir).resolve()
    new_dir = Path(args.new_dir).resolve() if args.new_dir else REPO_ROOT
    if not old_dir.is_dir() or not new_dir.is_dir():
        print("[error] 源码目录不存在", file=sys.stderr)
        return 2
    local_tables = index_local_tables(local_docs)
    old_sql = load_source_sql_tables(old_dir)
    new_sql = load_source_sql_tables(new_dir)
    sql_changes = diff_sql_docs(
        SqlDocument(old_dir / "sql", "", tables=old_sql),
        SqlDocument(new_dir / "sql", "", tables=new_sql),
        local_tables,
    )
    covered = {c.table for c in sql_changes if c.action in ("create_table", "alter_table", "alter_columns")}
    old_do = load_do_tables(old_dir)
    new_do = load_do_tables(new_dir)
    provider = style_provider_factory(mapping, local_docs)
    do_changes = diff_do_tables(old_do, new_do, provider, covered)
    changes = [c for c in sql_changes if c.action != "data"] + do_changes
    data_changes = [c for c in sql_changes if c.action == "data"] if args.include_data else []
    mapper_items = mapper_review(old_dir, new_dir, covered)
    current_do = load_do_tables(REPO_ROOT)
    for change in changes + data_changes:
        if change.action in ("create_routine", "alter_routine", "drop_routine"):
            change.target_file = resolve_routine_target(change, mapping, local_docs, local_tables)
        else:
            module = find_do_module_for_table(change.table, new_do) or find_do_module_for_table(change.table, current_do)
            change.target_file = mapping.target_file_for(change.table, module, local_tables)
        change.compute_hash()
        local_entry = local_tables.get(change.table)
        if change.action in ("create_table", "alter_table", "alter_columns") and local_entry:
            if change.new_table and local_entry[1].signature_hash() == change.new_table.signature_hash():
                change.status = "already_synced"
            elif change.action == "create_table":
                change.status = "already_exists"
        if change.action in ("create_routine", "alter_routine") and change.target_file:
            local_doc = local_docs.get(change.target_file)
            local_routine = local_doc.routines.get(change.table.lower()) if local_doc else None
            if local_routine and change.routine and local_routine.signature() == change.routine.signature():
                change.status = "already_synced"
    unresolved = [c for c in changes if not c.target_file]
    changes, ignored = split_changes_by_writable(changes, mapping)
    data_changes, ignored_data = split_changes_by_writable(data_changes, mapping)
    ignored.extend(ignored_data)
    upstream_inserts = {name: table.inserts for name, table in new_sql.items()}
    edited, apply_errors, applied = apply_changes(
        changes + data_changes,
        mapping,
        local_docs,
        upstream_inserts if args.include_data else None,
        include_data=args.include_data,
        allow_drop=args.allow_drop,
    )
    errors = apply_errors + validate_before_write(local_docs, edited)
    hard_errors = [e for e in errors if e.get("level") == "error"]
    mysql_result: dict[str, Any] = {"status": "skipped", "reason": "未启用 --mysql-validate"}
    if args.mysql_validate and not hard_errors:
        mysql_result = mysql_validate_docs(edited)
        if mysql_result.get("status") == "failed":
            hard_errors.append({"level": "error", "message": "MySQL 导入校验失败"})
    rename_map, rename_errors = plan_sql_renames([rel for rel, doc in edited.items() if not doc.readonly])
    hard_errors.extend({"level": "error", "message": message} for message in rename_errors)
    status = "success" if not hard_errors else "failed"
    previous_version = mapping.data.get("last_synced_version")
    applied_renames: dict[str, str] = {}
    if args.write and not hard_errors:
        for rel, doc in edited.items():
            if doc.readonly:
                continue
            update_header_date(doc)
            write_text(REPO_ROOT / rel, doc.render(), doc.bom)
        applied_renames, rename_apply_errors = apply_sql_renames(rename_map)
        hard_errors.extend({"level": "error", "message": message} for message in rename_apply_errors)
        if applied_renames:
            update_mapping_paths(mapping, applied_renames)
        for rel, doc in edited.items():
            if doc.readonly:
                continue
            final_rel = applied_renames.get(rel, rel)
            mapping.update_baseline(final_rel, args.version, doc)
            if final_rel != rel:
                mapping.data.get("files", {}).pop(rel, None)
        if args.version:
            mapping.data["last_synced_version"] = args.version
        mapping.save()
        status = "success" if not hard_errors else "failed"
    elif not args.write and not hard_errors:
        status = "dry_run"
    payload = {
        "sync_id": sync_id(),
        "tool_version": TOOL_VERSION,
        "operation_time": timestamp_iso(),
        "upstream_version": args.version,
        "previous_version": previous_version,
        "sources": {"old_dir": old_dir.as_posix(), "new_dir": new_dir.as_posix()},
        "renames": rename_payload(applied_renames if args.write else rename_map),
        "changes": [change_to_json(c) for c in changes],
        "data_changes": [change_to_json(c) for c in data_changes],
        "applied": applied,
        "unmapped": [{"table": c.table, "reason": "找不到已存在的目标 SQL 文件"} for c in unresolved],
        "ignored": ignored,
        "mapper_review": mapper_items,
        "needs_review": [x for c in changes for x in c.needs_review if x],
        "validation": {"errors": errors, "mysql": mysql_result},
        "status": status,
        "write": bool(args.write),
    }
    if args.write or args.audit:
        path = write_audit(payload)
        print(f"[audit] {path.relative_to(REPO_ROOT).as_posix()}")
    # 输出
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"同步 {old_dir} -> {new_dir}（{status}）")
        print(f"变更 {len(changes)} 项，已应用 {sum(1 for x in applied if x['status'] in ('created','altered','replaced','dropped','data_appended'))} 项，跳过 {sum(1 for x in applied if x['status']=='skipped')} 项")
        for item in applied:
            print(f"  - {item['table']}: {item['status']}" + (f"（{item.get('reason')}）" if item.get("reason") else ""))
        if ignored:
            print(f"忽略（只读脚本）{len(ignored)} 项：")
            for item in ignored:
                print(f"  - {item['table']}（{item['reason']}）")
        rename_info = applied_renames if args.write else rename_map
        if rename_info:
            print(f"{'脚本改名' if args.write else '脚本将改名'} {len(rename_info)} 项：")
            for old_rel, new_rel in sorted(rename_info.items()):
                print(f"  - {old_rel} -> {new_rel}")
        if mapper_items:
            print(f"Mapper XML 变更需人工确认 {len(mapper_items)} 项：")
            for item in mapper_items:
                print(f"  - {item['table']}（{item['files']}）")
        if errors:
            print("校验问题：")
            for err in errors:
                print(f"  - [{err['level']}] {err['message']}")
    if args.write and not hard_errors:
        # 写入后再次校验
        after_docs = load_local_documents(mapping)
        post_errors = []
        for rel in edited:
            final_rel = applied_renames.get(rel, rel)
            if final_rel in after_docs:
                post_errors.extend(validate_document(after_docs[final_rel]))
        post_errors = [e for e in post_errors if e["level"] == "error"]
        if post_errors:
            print("[error] 写入后校验失败", file=sys.stderr)
            for err in post_errors:
                print(f"  - [{err['level']}] {err['message']}", file=sys.stderr)
            return 1
    return 0 if not hard_errors else 1


def cmd_backfill(args: argparse.Namespace, mapping: Mapping, local_docs: dict[str, SqlDocument]) -> int:
    local_tables = index_local_tables(local_docs)
    do_tables = load_do_tables(REPO_ROOT)
    skip = mapping.skip_tables
    provider = style_provider_factory(mapping, local_docs)
    version = args.version or project_version()
    source_tables: dict[str, TableSchema] = {}
    if getattr(args, "source_dir", None):
        source_tables = load_source_sql_tables(Path(args.source_dir).resolve())
    changes: list[Change] = []
    unmapped: list[dict[str, str]] = []
    for name, do in sorted(do_tables.items()):
        if name in skip:
            continue
        if name in local_tables and args.tables and name not in args.tables:
            continue
        if name in local_tables:
            if not args.columns:
                continue
            style = provider(do)
            derived = derive_table(do, style)
            rel, current = local_tables[name]
            col_changes = []
            current_cols = {c.name.lower(): c for c in current.columns}
            for col in derived.columns:
                existing = current_cols.get(col.name.lower())
                if not existing:
                    col_changes.append({"action": "add_column", "column": col.name, "definition": col.definition, "origin": "backfill", "review": col.review})
            if col_changes:
                change = Change("alter_columns", name, "backfill", new_table=derived, column_changes=col_changes)
                change.target_file = rel
                change.needs_review = [c.get("review") for c in col_changes if c.get("review")]
                change.compute_hash()
                changes.append(change)
            continue
        if args.tables and name not in args.tables:
            continue
        target = mapping.target_file_for(name, do.module, local_tables)
        if not target:
            unmapped.append({"table": name, "reason": "找不到已存在的目标 SQL 文件", "module": do.module})
            continue
        style = style_for_module(do.module, mapping, local_docs)
        origin = "backfill"
        if name in source_tables:
            derived = source_tables[name]
            origin = "upstream_sql"
            inserts = list(derived.inserts) if getattr(args, "include_data", False) else []
        else:
            derived = derive_table(do, style)
            inserts = []
        change = Change("create_table", name, origin, target_file=target, new_table=derived, new_inserts=inserts)
        change.needs_review = list(derived.review)
        # 索引无法从代码推导
        if not derived.indexes or [i.kind for i in derived.indexes] == ["primary"]:
            change.needs_review.append("索引仅包含主键，需按上游 SQL 或实际查询补充")
        change.compute_hash()
        changes.append(change)
    edited, apply_errors, applied = apply_changes(
        changes,
        mapping,
        local_docs,
        None,
        include_data=getattr(args, "include_data", False),
        allow_drop=False,
    )
    errors = apply_errors + validate_before_write(local_docs, edited)
    hard_errors = [e for e in errors if e.get("level") == "error"]
    mysql_result: dict[str, Any] = {"status": "skipped", "reason": "未启用 --mysql-validate"}
    if args.mysql_validate and not hard_errors:
        mysql_result = mysql_validate_docs(edited)
        if mysql_result.get("status") == "failed":
            hard_errors.append({"level": "error", "message": "MySQL 导入校验失败"})
    rename_map, rename_errors = plan_sql_renames([rel for rel, doc in edited.items() if not doc.readonly])
    hard_errors.extend({"level": "error", "message": message} for message in rename_errors)
    status = "success" if not hard_errors else "failed"
    if not args.write and not hard_errors:
        status = "dry_run"
    applied_renames: dict[str, str] = {}
    if args.write and not hard_errors:
        for rel, doc in edited.items():
            update_header_date(doc)
            write_text(REPO_ROOT / rel, doc.render(), doc.bom)
        applied_renames, rename_apply_errors = apply_sql_renames(rename_map)
        hard_errors.extend({"level": "error", "message": message} for message in rename_apply_errors)
        if applied_renames:
            update_mapping_paths(mapping, applied_renames)
        for rel, doc in edited.items():
            final_rel = applied_renames.get(rel, rel)
            mapping.update_baseline(final_rel, version, doc)
            if final_rel != rel:
                mapping.data.get("files", {}).pop(rel, None)
        mapping.save()
        status = "success" if not hard_errors else "failed"
    payload = {
        "sync_id": sync_id(),
        "tool_version": TOOL_VERSION,
        "operation_time": timestamp_iso(),
        "upstream_version": version,
        "previous_version": mapping.data.get("last_synced_version"),
        "sources": {"code_root": REPO_ROOT.as_posix()},
        "renames": rename_payload(applied_renames if args.write else rename_map),
        "changes": [change_to_json(c) for c in changes],
        "applied": applied,
        "unmapped": unmapped,
        "needs_review": [x for c in changes for x in c.needs_review if x],
        "validation": {"errors": errors, "mysql": mysql_result},
        "status": status,
        "write": bool(args.write),
    }
    if args.write or args.audit:
        path = write_audit(payload)
        print(f"[audit] {path.relative_to(REPO_ROOT).as_posix()}")
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"回填（{status}）：{len(changes)} 项")
        for change in changes:
            print(f"  - {change.describe()} -> {change.target_file or '（未映射）'}")
            for item in change.column_changes[:5]:
                print(f"      {item['action']}: {item.get('column', '')}")
        for item in unmapped:
            print(f"  - 未映射 {item['table']}（模块 {item['module']}）")
        rename_info = applied_renames if args.write else rename_map
        if rename_info:
            print(f"{'脚本改名' if args.write else '脚本将改名'} {len(rename_info)} 项：")
            for old_rel, new_rel in sorted(rename_info.items()):
                print(f"  - {old_rel} -> {new_rel}")
        if errors:
            print("校验问题：")
            for err in errors:
                print(f"  - [{err['level']}] {err['message']}")
    return 0 if not hard_errors else 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SQL 脚本同步管理工具")
    parser.add_argument("--mapping", default=str(DEFAULT_MAPPING), help="mapping.json 路径")
    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check", help="当前代码与 SQL 脚本的漂移")
    p_check.add_argument("--json", action="store_true")

    p_base = sub.add_parser("baseline", help="按当前脚本刷新 mapping.json 基线")
    p_base.add_argument("--write", action="store_true")
    p_base.add_argument("--version")

    p_diff = sub.add_parser("diff", help="对比新旧源码包")
    p_diff.add_argument("--old-dir", required=True)
    p_diff.add_argument("--new-dir")
    p_diff.add_argument("--version")
    p_diff.add_argument("--json", action="store_true")

    p_sync = sub.add_parser("sync", help="执行同步")
    p_sync.add_argument("--old-dir", required=True)
    p_sync.add_argument("--new-dir")
    p_sync.add_argument("--version")
    p_sync.add_argument("--write", action="store_true")
    p_sync.add_argument("--include-data", action="store_true")
    p_sync.add_argument("--allow-drop", action="store_true")
    p_sync.add_argument("--audit", action="store_true")
    p_sync.add_argument("--mysql-validate", action="store_true", help="用 SQLSYNC_MYSQL_CMD 导入临时库校验")
    p_sync.add_argument("--json", action="store_true")

    p_bf = sub.add_parser("backfill", help="用当前代码补齐脚本缺失的表")
    p_bf.add_argument("--write", action="store_true")
    p_bf.add_argument("--columns", action="store_true", help="同时补齐缺失字段")
    p_bf.add_argument("--source-dir", help="包含上游 sql/ 的源码包，优先使用其中的权威 DDL")
    p_bf.add_argument("--include-data", action="store_true", help="新表同时写入上游初始化数据")
    p_bf.add_argument("--tables", nargs="*")
    p_bf.add_argument("--version")
    p_bf.add_argument("--audit", action="store_true")
    p_bf.add_argument("--mysql-validate", action="store_true", help="用 SQLSYNC_MYSQL_CMD 导入临时库校验")
    p_bf.add_argument("--json", action="store_true")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    parser = build_parser()
    args = parser.parse_args(argv)
    mapping_path = Path(args.mapping)
    if not mapping_path.exists():
        print(f"[error] mapping.json 不存在: {mapping_path}", file=sys.stderr)
        return 2
    mapping = Mapping.load(mapping_path)
    local_docs = load_local_documents(mapping)
    if args.command == "check":
        return cmd_check(args, mapping, local_docs)
    if args.command == "baseline":
        return cmd_baseline(args, mapping, local_docs)
    if args.command == "diff":
        return cmd_diff(args, mapping, local_docs)
    if args.command == "sync":
        return cmd_sync(args, mapping, local_docs)
    if args.command == "backfill":
        return cmd_backfill(args, mapping, local_docs)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
