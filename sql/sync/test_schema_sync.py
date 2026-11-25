#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""schema_sync 的回归测试（标准库 unittest，无第三方依赖）。

运行：
    python sql/sync/test_schema_sync.py
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import schema_sync as ss  # noqa: E402


def sample_doc() -> str:
    return """SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ----------------------------
-- Table structure for demo_user
-- ----------------------------
DROP TABLE IF EXISTS `demo_user`;
CREATE TABLE `demo_user`  (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '编号',
  `name` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '名称',
  `status` tinyint NOT NULL DEFAULT 0 COMMENT '状态',
  `creator` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_name`(`name` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '用户表';

-- ----------------------------
-- Records of demo_user
-- ----------------------------
BEGIN;
INSERT INTO `demo_user` (`id`, `name`, `status`, `creator`, `create_time`, `updater`, `update_time`, `deleted`) VALUES (1, 'a', 0, '', '2026-01-01 00:00:00', '', '2026-01-01 00:00:00', b'0');
COMMIT;

SET FOREIGN_KEY_CHECKS = 1;
"""


def do_source(fields: str, table: str = "demo_user", parent: str = "TenantBaseDO") -> str:
    return f"""package x;

import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

/**
 * 用户表
 */
@TableName("{table}")
@Data
public class DemoUserDO extends {parent} {{

{fields}
}}
"""


class SqlParseTest(unittest.TestCase):
    def test_parse_table(self) -> None:
        doc = ss.parse_sql_text(sample_doc(), Path("demo.sql"))
        self.assertEqual(list(doc.tables), ["demo_user"])
        table = doc.tables["demo_user"]
        self.assertEqual(len(table.columns), 8)
        self.assertEqual(table.pk(), ["id"])
        self.assertEqual(table.comment, "用户表")
        self.assertEqual(table.column("name").type, "varchar(64)")
        self.assertFalse(table.column("name").nullable)
        self.assertEqual(table.column("status").default, "0")
        self.assertEqual(table.inserts[0][:11], "INSERT INTO")
        self.assertGreaterEqual(doc.tail_start, 0)
        self.assertIn("SET FOREIGN_KEY_CHECKS = 1", doc.lines[doc.tail_start])

    def test_parse_routine(self) -> None:
        sql = sample_doc() + """
DELIMITER ;;
CREATE PROCEDURE `p_demo`()
BEGIN
  SELECT * FROM demo_user;
END ;;
DELIMITER ;
"""
        doc = ss.parse_sql_text(sql, Path("demo.sql"))
        routine = doc.routines["p_demo"]
        self.assertEqual(routine.kind, "procedure")
        self.assertIn("DELIMITER ;", routine.raw)

    def test_do_parse(self) -> None:
        fields = """    /**
     * 名称
     */
    private String name;
    @TableField(exist = false)
    private String ignoreMe;
    @TableField(typeHandler = Jackson3TypeHandler.class)
    private List<Long> itemIds;
"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "full-module-demo"
            path = root / "src/main/java/x/dal/dataobject/DemoUserDO.java"
            path.parent.mkdir(parents=True)
            path.write_text(do_source(fields), encoding="utf-8")
            table = ss.parse_do_file(path)
        self.assertIsNotNone(table)
        self.assertEqual(table.name, "demo_user")
        self.assertEqual(table.module, "demo")
        self.assertEqual(table.parent, "TenantBaseDO")
        names = [f.name for f in table.fields]
        self.assertEqual(names, ["name", "ignoreMe", "itemIds"])
        self.assertFalse(table.fields[1].exist)
        self.assertTrue(table.fields[2].is_json)

    def test_primitive_java_type(self) -> None:
        path = Path("C:/tmp/full-module-demo/src/main/java/x/dal/dataobject/DemoProductDO.java")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "full-module-demo/src/main/java/x/dal/dataobject/DemoProductDO.java"
            path.parent.mkdir(parents=True)
            path.write_text(do_source("    /**\n     * 单位\n     */\n    private int unit;\n", table="demo_product", parent="BaseDO"), encoding="utf-8")
            table = ss.parse_do_file(path)
        derived = ss.derive_table(table, ss.StyleContext())
        self.assertEqual(derived.column("unit").type, "int")


class FilenameDateTest(unittest.TestCase):
    def test_dated_sql_filename(self) -> None:
        when = datetime(2026, 11, 25)
        self.assertEqual(ss.dated_sql_filename("ai-2026-11-01.sql", when), "ai-2026-11-25.sql")
        self.assertEqual(ss.dated_sql_filename("crm2026-09-19.sql", when), "crm2026-11-25.sql")
        self.assertEqual(ss.dated_sql_filename("mes-206-09-26.sql", when), "mes-2026-11-25.sql")
        self.assertEqual(ss.dated_sql_filename("ruoyi-vue-pro.sql", when), "ruoyi-vue-pro.sql")
        self.assertEqual(
            ss.dated_sql_filename("jimureport.mysql5.7.create.sql", when),
            "jimureport.mysql5.7.create.sql",
        )

    def test_update_mapping_paths(self) -> None:
        mapping = ss.Mapping(
            {
                "modules": {"ai": {"files": ["sql/mysql/ai/old-2026-01-01.sql"]}},
                "explicit_tables": {"report_x": "sql/mysql/report/ureport.sql"},
                "files": {"sql/mysql/ai/old-2026-01-01.sql": {"last_synced_version": "x"}},
            },
            Path("mapping.json"),
        )
        ss.update_mapping_paths(mapping, {"sql/mysql/ai/old-2026-01-01.sql": "sql/mysql/ai/new-2026-11-25.sql"})
        self.assertEqual(mapping.data["modules"]["ai"]["files"], ["sql/mysql/ai/new-2026-11-25.sql"])
        self.assertIn("sql/mysql/ai/new-2026-11-25.sql", mapping.data["files"])
        self.assertNotIn("sql/mysql/ai/old-2026-01-01.sql", mapping.data["files"])
        self.assertEqual(mapping.data["explicit_tables"]["report_x"], "sql/mysql/report/ureport.sql")


class DiffApplyTest(unittest.TestCase):
    def _doc(self, sql: str) -> ss.SqlDocument:
        return ss.parse_sql_text(sql, Path("demo.sql"))

    def test_sql_create(self) -> None:
        old = self._doc(sample_doc())
        new_sql = sample_doc().replace("COMMIT;", "COMMIT;").replace(
            "SET FOREIGN_KEY_CHECKS = 1;",
            """-- ----------------------------
-- Table structure for demo_role
-- ----------------------------
DROP TABLE IF EXISTS `demo_role`;
CREATE TABLE `demo_role`  (
  `id` bigint NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '角色';

SET FOREIGN_KEY_CHECKS = 1;""",
        )
        new = self._doc(new_sql)
        changes = ss.diff_sql_docs(old, new, {})
        self.assertEqual([(c.action, c.table) for c in changes], [("create_table", "demo_role")])

    def test_apply_create_and_alter(self) -> None:
        doc = self._doc(sample_doc())
        table = ss.TableSchema(
            "demo_role",
            [ss.Column("id", "bigint", "`id` bigint NOT NULL AUTO_INCREMENT")],
            [ss.IndexDef("PRIMARY", ["id"], True, "primary", "PRIMARY KEY (`id`) USING BTREE")],
            "角色",
            "ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '角色'",
        )
        ss.apply_create_table(doc, table)
        self.assertIn("demo_role", doc.tables)
        self.assertTrue(doc.render().rstrip().endswith("SET FOREIGN_KEY_CHECKS = 1;"))
        # 表名字典序：demo_role < demo_user
        self.assertEqual(list(doc.tables)[:2], ["demo_role", "demo_user"])

    def test_add_column_is_idempotent(self) -> None:
        doc = self._doc(sample_doc())
        current = doc.tables["demo_user"]
        new_table = ss.TableSchema(
            "demo_user",
            columns=list(current.columns) + [
                ss.Column(
                    "email",
                    "varchar(128)",
                    "`email` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '邮箱'",
                    nullable=True,
                    comment="邮箱",
                )
            ],
            indexes=list(current.indexes),
            comment=current.comment,
            options_tail=current.options_tail,
        )
        mapping = ss.Mapping(
            {
                "sql_root": "sql/mysql",
                "readonly_files": [],
                "skip_tables": [],
                "explicit_tables": {},
                "modules": {},
                "files": {},
            },
            Path("mapping.json"),
        )
        change = ss.Change(
            "alter_columns",
            "demo_user",
            "code_do",
            new_table=new_table,
            target_file="local.sql",
            column_changes=[
                {"action": "add_column", "column": "email", "definition": new_table.column("email").definition}
            ],
        )
        edited, errors, applied = ss.apply_changes(
            [change], mapping, {"local.sql": doc}, None, include_data=False, allow_drop=False
        )
        self.assertEqual(errors, [])
        self.assertEqual(applied[0]["status"], "altered")
        self.assertIn("email", [c.name for c in edited["local.sql"].tables["demo_user"].columns])
        # 第二次执行应识别为已同步
        again, errors, applied = ss.apply_changes(
            [change], mapping, {"local.sql": edited["local.sql"]}, None, include_data=False, allow_drop=False
        )
        self.assertEqual(errors, [])
        self.assertEqual(applied[0]["reason"], "already_synced")

    def test_validation_catches_insert_mismatch(self) -> None:
        bad = sample_doc().replace(
            "(1, 'a', 0, '', '2026-01-01 00:00:00', '', '2026-01-01 00:00:00', b'0')",
            "(1, 'a', 0, '', '2026-01-01 00:00:00', '', '2026-01-01 00:00:00')",
        )
        doc = self._doc(bad)
        errors = ss.validate_document(doc)
        self.assertTrue(any("值个数" in e["message"] for e in errors))

    def test_rewrite_insert_when_column_removed(self) -> None:
        line = (
            "INSERT INTO `demo_user` (`id`, `name`, `status`, `creator`, `create_time`, `updater`, `update_time`, `deleted`) "
            "VALUES (1, 'a', 0, '', '2026-01-01 00:00:00', '', '2026-01-01 00:00:00', b'0');"
        )
        valid = {"id", "name", "creator", "create_time", "updater", "update_time", "deleted"}
        new_line = ss.rewrite_insert_line(line, valid)
        self.assertNotIn("`status`", new_line)
        self.assertEqual(ss.count_tuple_values(new_line.split("VALUES", 1)[1]), 7)

    def test_readonly_filter(self) -> None:
        mapping = ss.Mapping(
            {
                "sql_root": "sql/mysql",
                "readonly_files": ["sql/mysql/quartz.sql"],
                "skip_tables": [],
                "explicit_tables": {},
                "modules": {},
                "files": {},
            },
            Path("mapping.json"),
        )
        change = ss.Change("create_table", "qrtz_test", "upstream_sql", target_file="sql/mysql/quartz.sql")
        writable, ignored = ss.split_changes_by_writable([change], mapping)
        self.assertEqual(writable, [])
        self.assertEqual(len(ignored), 1)

    def test_routine_diff_and_apply(self) -> None:
        base = sample_doc()
        def with_proc(value: str) -> str:
            return base + f"""
DELIMITER ;;
CREATE PROCEDURE `p_demo`()
BEGIN
  SELECT {value} FROM demo_user;
END ;;
DELIMITER ;
"""
        old = self._doc(with_proc("1"))
        new = self._doc(with_proc("2"))
        local = self._doc(base)
        changes = ss.diff_sql_docs(old, new, {"demo_user": ("local.sql", local.tables["demo_user"])})
        self.assertEqual([c.action for c in changes], ["alter_routine"])
        mapping = ss.Mapping(
            {
                "sql_root": "sql/mysql",
                "readonly_files": [],
                "skip_tables": [],
                "explicit_tables": {},
                "modules": {},
                "files": {},
            },
            Path("mapping.json"),
        )
        for change in changes:
            change.target_file = ss.resolve_routine_target(
                change, mapping, {"local.sql": local}, {"demo_user": ("local.sql", local.tables["demo_user"])}
            )
        edited, errors, applied = ss.apply_changes(
            changes, mapping, {"local.sql": local}, None, include_data=False, allow_drop=False
        )
        self.assertEqual(errors, [])
        self.assertEqual(applied[0]["status"], "created")
        text = edited["local.sql"].render()
        self.assertIn("SELECT 2 FROM demo_user;", text)
        self.assertIn("DELIMITER ;", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
