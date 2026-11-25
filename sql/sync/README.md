# SQL 脚本同步管理

把上游开源项目的数据库变更同步到本项目**已有的** MySQL 脚本中。工具不创建新的 SQL 文件，所有修改都写入 `sql/mysql/` 下现有的 Navicat 导出脚本。

## 目录

```text
sql/sync/
├── schema_sync.py      解析、差异、写入、校验、审计（Python 标准库）
├── mapping.json        表/模块 → 脚本文件映射，只读名单，各文件基线
├── audit/              每次同步产生一个 JSON 审计文件
└── README.md
```

配套技能：`.claude/skills/sql-sync/SKILL.md`，在 Claude Code 中执行 `/sql-sync` 即可按流程操作。

## 需求对应

| 需求 | 实现 |
| --- | --- |
| 代码与 Schema 的关联映射 | `mapping.json` + 解析 `@TableName`/DO 字段 + 上游 `sql/` 差异；模块、表、文件三级归属 |
| 推导 SQL 调整 | 上游 SQL 差异直接采用权威 DDL；DO 差异推导新增/修改/删除列；例程、索引、约束、数据来自 SQL 差异 |
| 不新建独立 SQL 文件 | 表已存在则写回原文件；新表按模块/前缀写入既有脚本；找不到目标文件只报告 `unmapped`，绝不新建 |
| 变更审计 | 每次 `--write` 在 `sql/sync/audit/` 生成 JSON，含来源、版本、时间、变更前后内容、校验结果 |
| 变更校验 | 结构/索引/INSERT 一致性检查 + 可选 sqlglot 语法校验 + 可选临时 MySQL 库导入 |
| 增量更新 | `mapping.json` 基线指纹 + 当前表指纹比对 + 逐列去重；重复执行 0 变更 |
| 格式一致性 | UTF-8/无 BOM/LF、Navicat 分段、表名字典序、只替换变更块，未变更字节保留 |

## 快速开始

```bash
# 1. 检查当前代码与 SQL 脚本的漂移（只读）
python sql/sync/schema_sync.py check

# 2. 对比新旧两个上游源码包（只读）
python sql/sync/schema_sync.py diff \
  --old-dir /path/to/upstream-2026.09 \
  --new-dir /path/to/upstream-2026.10 \
  --version v2026.10

# 3. 预演同步，不写文件
python sql/sync/schema_sync.py sync \
  --old-dir /path/to/upstream-2026.09 \
  --new-dir /path/to/upstream-2026.10 \
  --version v2026.10

# 4. 确认后落盘（自动校验、写审计）
python sql/sync/schema_sync.py sync \
  --old-dir /path/to/upstream-2026.09 \
  --new-dir /path/to/upstream-2026.10 \
  --version v2026.10 --write

# 5. 用当前代码补齐脚本中缺失的表（默认预演）
python sql/sync/schema_sync.py backfill --write
# 同时补齐缺失字段
python sql/sync/schema_sync.py backfill --write --columns
# 若上游源码包包含业务模块 DDL，优先用其中的权威定义（含索引、初始化数据）
python sql/sync/schema_sync.py backfill --write --source-dir /path/to/upstream

# 6. 按当前脚本刷新基线（版本号写入 mapping.json）
python sql/sync/schema_sync.py baseline --write --version 2026.10-jdk25-SNAPSHOT
```

`--old-dir` / `--new-dir` 可以是完整源码包，也可以是只包含 `sql/`、`full-module-*`（或 `yudao-module-*`）的目录。`--new-dir` 省略时使用当前仓库。

所有命令都支持 `--json`，便于 CI / 脚本消费。

回归测试：

```bash
python sql/sync/test_schema_sync.py
```

## 变更识别

按优先级合并两类来源：

| 优先级 | 来源 | 可识别 | 可靠性 |
| --- | --- | --- | --- |
| 1 | 上游新旧源码包中 `sql/` 目录的差异 | 表、字段、类型、默认值、注释、主键、索引、唯一约束、初始化数据、存储过程/函数/视图/触发器 | 高，直接采用上游新版本原文 |
| 2 | 上游新旧源码包中 `*DO.java` 的差异 | 表、字段、Java 类型、是否可空 | 中，只能生成列定义 |
| 3 | 当前代码 vs 当前 SQL（`check` / `backfill`） | 缺失表、缺失列、类型漂移 | 用于回填 |

Java 代码中**没有**索引、唯一约束、存储过程、初始化数据，因此：

- 上游 SQL 有对应差异时，索引/约束/数据/例程会一并同步；
- 只有代码差异（上游 SQL 也没有）时，只同步列，索引和初始化数据无法推导，会记录在 `needs_review` / `mapper_review` 中交人工确认；
- Mapper XML 有变更时，工具会列出涉及的表并提示检查索引、约束、查询字段。

### 字段来源优先级

`--old-dir` / `--new-dir` 的目录结构：

```text
<source>/
├── sql/mysql/ruoyi-vue-pro.sql        # 若存在，作为权威 DDL 来源
└── full-module-*/                       # DO 源码（也兼容 yudao-module-*）
    └── .../dal/dataobject/**/*DO.java
```

上游 `sql/` 只包含 system/infra 等核心表时，业务模块表只能从 DO 推导，这是上游发布包本身的限制，不是工具遗漏。

## 文件归属

`mapping.json` 维护映射：

- `modules`：模块名 → 模块源码目录 + 目标脚本文件；
- `explicit_tables`：个别表（如 `report_go_view_project`）直接指定文件；
- `readonly_files`：第三方脚本，只读，不参与同步：
  - `sql/mysql/quartz.sql`
  - `sql/mysql/report/jimureport.mysql5.7.create.sql`
  - `sql/mysql/report/go-view.sql`
- `skip_tables`：脚本中存在、但没有 DO 的正常表（如 Seata 的 `undo_log`）。

表已存在于某个脚本时优先写回该文件；否则按模块、显式映射、前缀匹配依次查找；仍找不到则记为 `unmapped`，**不会新建文件**。

## 增量与幂等

- `mapping.json` 的 `files.<脚本>` 保存 `last_synced_version`、`schema_fingerprint` 和每张表的 `tables.<表名>` 指纹。
- 同步时先比较「当前脚本中的表」与「本次目标表」的指纹：一致则跳过（`already_synced`）。
- 列级变更逐列去重：已存在的 `add_column`、已不存在的 `modify/drop_column` 自动忽略。
- 重复执行同一对新旧源码包，第二次结果应为 0 变更。
- `--from` / `--to` 版本号用于审计；实际差异由两个源码目录的内容决定。
- 初次接管或大规模人工修改脚本后，运行 `baseline --write --version <当前版本>` 重建指纹；否则基线只反映上次工具写入时的状态。

## 校验

写入前在内存中进行，失败则不落盘：

- 重新解析改动后的文件，表/例程数量一致；
- 列名不重复；主键存在（无主键仅警告）；索引引用的列存在；
- `INSERT` 的列都在 `CREATE TABLE` 中，且每条 `INSERT` 的值个数与列数一致；
- BOM、换行风格不变；只读文件未被修改；
- 例程的 `DELIMITER` 成对。

可选的真实数据库校验（需要本机 `mysql` 客户端）：

```bash
# 指定连接命令前缀，工具会创建临时库、导入、再删库
export SQLSYNC_MYSQL_CMD="mysql -h127.0.0.1 -P3306 -uroot -p123456"
python sql/sync/schema_sync.py sync ... --write --mysql-validate
```

未配置 `SQLSYNC_MYSQL_CMD` 时跳过，并在审计里注明「未做真实执行校验」。

## 审计

每次实际写入（`--write`）都会在 `sql/sync/audit/` 生成一个 JSON 文件：

```json
{
  "sync_id": "20261125-102749-044354",
  "operation_time": "2026-11-25T10:27:49+08:00",
  "upstream_version": "v2026.10",
  "previous_version": "v2026.09",
  "sources": {"old_dir": "...", "new_dir": "..."},
  "renames": [
    {"from": "sql/mysql/ai/ai-2026-11-01.sql", "to": "sql/mysql/ai/ai-2026-11-25.sql"}
  ],
  "changes": [
    {
      "action": "add_column",
      "table": "ai_image",
      "origin": "backfill",
      "target_file": "sql/mysql/ai/ai-2026-11-25.sql",
      "change_hash": "…",
      "before": null,
      "after": {"name": "ai_image", "columns": ["…"]},
      "needs_review": []
    }
  ],
  "applied": [{"table": "ai_drama_audio", "status": "created", "file": "..."}],
  "ignored": [],
  "unmapped": [],
  "mapper_review": [],
  "validation": {"errors": []},
  "status": "success"
}
```

失败时同样落一条 `failed` 记录；预演（不带 `--write`）默认不写审计，加 `--audit` 可单独留下预演结果。

## 格式保持

- 读取时检测 BOM 与换行（全部脚本为 UTF-8 无 BOM、LF；`jimureport.mysql5.7.create.sql` 带 BOM，只读）。
- 只替换发生变更的 `CREATE TABLE` 列定义区或整块表定义，未变更行逐字节保留。
- 新表按表名字典序插入；沿用 Navicat 分段注释、两空格缩进、反引号、`CHARACTER SET` / `COLLATE` / `USING BTREE` 风格。
- 文件头 `Date:` 更新为本次操作时间。
- **文件名日期同步**：脚本被修改并写回后，文件名中的 `YYYY-MM-DD` 自动替换为当天日期（如 `ai-2026-11-01.sql` → `ai-2026-11-25.sql`；`crm2026-09-19.sql` → `crm2026-11-25.sql`；`mes-206-09-26.sql` → `mes-2026-11-25.sql`）。无日期的文件（`ruoyi-vue-pro.sql`、`ureport.sql` 等）不改名；目标文件已存在时整次写入中止，不覆盖。`mapping.json` 中的模块映射、基线键以及审计的 `renames` 会同步更新。
- 新增列插在业务字段末尾、公共字段（`creator`/`create_time`/...）之前。
- 修改已有表时保留本地独有的列与索引（三方合并：旧上游、新上游、本地）。

## 首次回填记录（2026-11-25）

以当前代码为准，向以下既有脚本回填：

- `sql/mysql/ai/ai-2026-11-25.sql`
  - 新增 17 张表：`ai_drama_audio`、`ai_drama_canvas`、`ai_drama_character`、`ai_drama_character_appearance`、`ai_drama_director`、`ai_drama_location`、`ai_drama_motion_reference`、`ai_drama_project`、`ai_drama_script`、`ai_drama_storyboard`、`ai_drama_video_submission`、`ai_drama_visual_asset`、`ai_ppt`、`ai_skill`、`ai_skill_file`、`ai_speech`、`ai_video`；
  - 补齐 `ai_chat_role`、`ai_image`、`ai_model`、`ai_music` 的 20 个缺失字段。
- `sql/mysql/iot/iot-2026-11-25.sql`：`iot_device_modbus_point.bit_index`。
- `sql/mysql/member/member-2026-11-25.sql`：`member_user.introduction`。

这些表/字段由 DO 推导，索引只包含主键；回填后人工复核，已将 14 个明显过短的 `varchar(64)` 文本列放宽为 `text` / `varchar(1024)`，记录见 `audit/review-20261125-backfill-types.json`。后续拿到包含业务模块 DDL 的上游包时，可用 `sync` 以权威 DDL 覆盖。

### 类型核对（2026-11-25）

对照上游 `v2026.10(jdk25)` 的 DO 与脚本初始化数据，修正了 5 处 SQL 列类型，并修复了工具对 Java 原生 `int` 的映射误报：

| 表.列 | 修正前 | 修正后 |
| --- | --- | --- |
| `crm_business_status.percent` | `decimal(24, 6)` | `int` |
| `crm_contact.owner_user_id` | `varchar(256)` | `bigint` |
| `hrm_performance_assessment_action_record.type` | `varchar(32)` | `tinyint` |
| `mp_menu.parent_id` | `varchar(32)` | `bigint` |
| `promotion_article.browse_count` | `varchar(255)` | `int NOT NULL DEFAULT 0` |
| `crm_product.unit` | `tinyint` | 保持不变（工具误报已修复） |

涉及列的现有初始化数据均为整数或 NULL，类型转换不会丢失精度。完整证据和已有数据库的 `ALTER TABLE` 语句见 `audit/review-20261125-type-alignment.json`；已有环境升级时执行其中 `migration_sql`。

## 已知限制

- 只有代码差异时，无法推导索引、唯一约束、初始数据、字段长度/精度/注释；这些不会自动写入。
- 不修改 `sql/quartz.sql` 等只读第三方脚本。
- 不处理非 MySQL 脚本（`sql/postgresql`、`sql/oracle` 等）；需要时用 `sql/tools/convertor.py` 从 MySQL 重新生成。
- 删除表/列默认只警告，需显式 `--allow-drop`。
- 数据同步默认关闭；`--include-data` 时只追加缺失的 `INSERT`，不删除本地已有数据。

## 维护

- 新增模块或表归属：编辑 `mapping.json` 的 `modules` / `explicit_tables`。
- 新增只读脚本：加入 `readonly_files`。
- 排查解析问题：先运行 `python sql/sync/schema_sync.py check --json`，确认表数、列数与 `grep -c '^CREATE TABLE'` 一致。
- 代码结构变化后，若 `check` 出现大量 `type_mismatch`，先确认 DO 字段类型是否确实变更，再决定是否手工调整 SQL；工具不会自动改类型。
