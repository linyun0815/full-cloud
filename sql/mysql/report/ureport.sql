-- UReport2 报表：模板表、菜单（仅 MySQL 5.7+）
-- 独立脚本：UReport2 的模板表与菜单只由本脚本初始化，新项目、已有项目开启 UReport2 时，都需要导入本脚本。
-- 菜单：[UReport2 报表] 菜单对应查看权限 report:ureport:query，[报表设计] 按钮对应设计权限 report:ureport:design。
-- 可重复执行：模板表已存在时不重建；菜单已存在时不再插入，不覆盖已有菜单与模板。
-- 升级：旧版本脚本的 [UReport2 报表] 菜单是设计权限，导入时会改为查看权限（菜单编号不变），并把原菜单的角色授权、
--      租户套餐同步到 [报表设计] 按钮，原来可以设计的角色仍然可以设计。新项目不会给任何角色自动分配菜单。
-- 同时统一 [报表管理] 下报表菜单的显示名称，只修改名称，不修改路由、组件、权限、排序等。

SET NAMES utf8mb4;

-- ----------------------------
-- Table structure for report_ureport_file
-- ----------------------------
CREATE TABLE IF NOT EXISTS `report_ureport_file` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '编号',
  `name` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT '模板名称，不包含存储前缀',
  `content` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '模板内容（UReport XML）',
  `creator` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = 'UReport2 报表模板表（删除时逻辑删除）';

START TRANSACTION;

-- ----------------------------
-- 菜单：报表管理 -> UReport2 报表（查看权限）
-- 父菜单按「报表管理」的路由地址 /report 查找，不依赖菜单编号；找不到父菜单时不插入
-- 已存在 UReport2 报表菜单（包括旧版本脚本的设计权限菜单）时不插入
-- ----------------------------
INSERT INTO `system_menu` (`name`, `permission`, `type`, `sort`, `parent_id`, `path`, `icon`, `component`, `component_name`, `status`, `visible`, `keep_alive`, `always_show`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
SELECT 'UReport2 报表', 'report:ureport:query', 2, 3, p.`id`, 'ureport', 'ep:document', 'report/ureport/index', 'UReport', 0, b'1', b'1', b'1', '1', NOW(), '1', NOW(), b'0'
FROM (
    SELECT `id` FROM `system_menu`
    WHERE `path` = '/report' AND `parent_id` = 0 AND `deleted` = b'0'
    ORDER BY `id` LIMIT 1
) p
WHERE NOT EXISTS (
    SELECT 1 FROM (
        SELECT `id` FROM `system_menu`
        WHERE `type` = 2 AND `component` = 'report/ureport/index'
          AND `permission` IN ('report:ureport:query', 'report:ureport:design') AND `deleted` = b'0'
        LIMIT 1
    ) m
);

SET @ureport_menu_id := (
    SELECT `id` FROM `system_menu`
    WHERE `type` = 2 AND `component` = 'report/ureport/index'
      AND `permission` IN ('report:ureport:query', 'report:ureport:design') AND `deleted` = b'0'
    ORDER BY `id` LIMIT 1
);
-- 是否为旧版本脚本的菜单（设计权限），需要升级
SET @ureport_upgrade := (
    SELECT COUNT(1) FROM `system_menu`
    WHERE `id` = @ureport_menu_id AND `permission` = 'report:ureport:design'
);

-- ----------------------------
-- 按钮：UReport2 报表 -> 报表设计（设计权限）
-- ----------------------------
INSERT INTO `system_menu` (`name`, `permission`, `type`, `sort`, `parent_id`, `path`, `icon`, `component`, `component_name`, `status`, `visible`, `keep_alive`, `always_show`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
SELECT '报表设计', 'report:ureport:design', 3, 1, @ureport_menu_id, '', '', '', NULL, 0, b'1', b'1', b'1', '1', NOW(), '1', NOW(), b'0'
FROM DUAL
WHERE @ureport_menu_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM (
        SELECT `id` FROM `system_menu`
        WHERE `parent_id` = @ureport_menu_id AND `type` = 3
          AND `permission` = 'report:ureport:design' AND `deleted` = b'0'
        LIMIT 1
    ) m
);

SET @ureport_design_menu_id := (
    SELECT `id` FROM `system_menu`
    WHERE `parent_id` = @ureport_menu_id AND `type` = 3
      AND `permission` = 'report:ureport:design' AND `deleted` = b'0'
    ORDER BY `id` LIMIT 1
);

-- ----------------------------
-- 升级：只处理旧版本脚本的设计权限菜单；升级完成后，菜单变为查看权限，重复执行时不再处理
-- ----------------------------
-- ① 角色：已分配 [UReport2 报表] 菜单的角色，同时分配 [报表设计] 按钮，保留原来的设计权限
INSERT INTO `system_role_menu` (`role_id`, `menu_id`, `creator`, `create_time`, `updater`, `update_time`, `deleted`, `tenant_id`)
SELECT r.`role_id`, @ureport_design_menu_id, '1', NOW(), '1', NOW(), b'0', r.`tenant_id`
FROM (
    SELECT DISTINCT rm.`role_id`, rm.`tenant_id` FROM `system_role_menu` rm
    WHERE rm.`menu_id` = @ureport_menu_id AND rm.`deleted` = b'0'
      AND NOT EXISTS (
          SELECT 1 FROM `system_role_menu` d
          WHERE d.`role_id` = rm.`role_id` AND d.`menu_id` = @ureport_design_menu_id AND d.`deleted` = b'0'
      )
) r
WHERE @ureport_upgrade = 1 AND @ureport_design_menu_id IS NOT NULL;

-- ② 租户套餐：包含 [UReport2 报表] 菜单的套餐，同时包含 [报表设计] 按钮。否则修改套餐时，租户管理员会失去该按钮
UPDATE `system_tenant_package`
SET `menu_ids` = JSON_ARRAY_APPEND(`menu_ids`, '$', @ureport_design_menu_id)
WHERE @ureport_upgrade = 1 AND @ureport_design_menu_id IS NOT NULL AND `deleted` = b'0'
  AND JSON_VALID(`menu_ids`)
  AND JSON_CONTAINS(`menu_ids`, CAST(@ureport_menu_id AS JSON))
  AND NOT JSON_CONTAINS(`menu_ids`, CAST(@ureport_design_menu_id AS JSON));

-- ③ 菜单：改为查看权限
UPDATE `system_menu`
SET `permission` = 'report:ureport:query', `updater` = '1', `update_time` = NOW()
WHERE @ureport_upgrade = 1 AND @ureport_design_menu_id IS NOT NULL
  AND `id` = @ureport_menu_id AND `permission` = 'report:ureport:design';

-- ----------------------------
-- 菜单名称：统一 [报表管理] 下的报表菜单名称
-- 只匹配父菜单为 /report 的固定组件，不影响其它同名菜单；名称已一致时不会更新
-- ----------------------------
UPDATE `system_menu` m
JOIN (
    SELECT `id` FROM `system_menu`
    WHERE `path` = '/report' AND `parent_id` = 0 AND `deleted` = b'0'
    ORDER BY `id` LIMIT 1
) p ON m.`parent_id` = p.`id`
SET m.`name` = CASE m.`component`
    WHEN 'report/ureport/index' THEN 'UReport2 报表'
    WHEN 'report/jmreport/index' THEN '积木报表'
    WHEN 'report/jmreport/bi' THEN '积木仪表盘'
    WHEN 'report/goview/index' THEN 'GoView 大屏'
END
WHERE m.`type` = 2 AND m.`deleted` = b'0'
  AND (
      (m.`component` = 'report/ureport/index' AND m.`permission` IN ('report:ureport:query', 'report:ureport:design'))
      OR (m.`component` IN ('report/jmreport/index', 'report/jmreport/bi', 'report/goview/index'))
  )
  -- 名称已一致（按字节比较）时不更新，避免重复执行时刷新 update_time
  AND CAST(m.`name` AS BINARY) <> CASE m.`component`
    WHEN 'report/ureport/index' THEN 'UReport2 报表'
    WHEN 'report/jmreport/index' THEN '积木报表'
    WHEN 'report/jmreport/bi' THEN '积木仪表盘'
    WHEN 'report/goview/index' THEN 'GoView 大屏'
  END;

COMMIT;
