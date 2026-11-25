# full-cloud 微服务版

基于 Spring Cloud 的微服务后端脚手架，采用「网关 + 业务服务 + 框架组件」的分层架构，业务模块可按需启停、独立部署。

- 技术基线：JDK 25、Spring Boot 4.1.2、Spring Cloud 2025.1.2、Spring Cloud Alibaba 2025.1.0.0
- 服务注册与配置：Nacos 3.x
- 数据存储：MySQL + Redis（MyBatis-Plus + Druid + Redisson）
- 前端为独立仓库（如 yudao-ui-admin-vue3 / yudao-ui-admin-vben），本仓库只包含后端

## 目录

- [一、技术栈](#一技术栈)
- [二、项目架构](#二项目架构)
- [三、启动指南](#三启动指南)
- [四、部署指南](#四部署指南)

## 一、技术栈

| 分类 | 技术 | 版本 |
| --- | --- | --- |
| 基础 | JDK / Maven | 25 / 3.8+ |
| 基础 | Spring Boot | 4.1.2 |
| 基础 | Spring Cloud / Spring Cloud Alibaba | 2025.1.2 / 2025.1.0.0 |
| 网关 | Spring Cloud Gateway（WebFlux） | 随 Spring Cloud |
| 注册 / 配置 | Nacos Client（服务端建议 3.x） | 3.1.1 |
| 数据 | MySQL / MyBatis-Plus / Druid | 8.x / 3.5.17 / 1.2.28 |
| 缓存 | Redis / Redisson | 7.x / 4.8.0 |
| 文档 | Springdoc + Knife4j | 3.1.1 / 4.5.0 |
| 工作流 | Flowable | 8.0.0 |
| 定时任务 | XXL-Job | 2.4.0 |
| AI | Spring AI 及国内主流大模型接入 | 2.0.1 |
| 监控 | Spring Boot Admin / SkyWalking / OpenTelemetry | 4.1.4 / 9.7.0 / 1.67.0 |
| 消息队列 | RocketMQ / RabbitMQ / Kafka | 按需引入 |
| 分布式 | Seata（脚本见 `script/seata`）、Sentinel（`script/sentinel`） | 按需引入 |

版本统一由 [full-dependencies/pom.xml](full-dependencies/pom.xml) 管理，业务模块不直接声明版本号。

## 二、项目架构

### 2.1 整体架构

```text
                          ┌───────────────────────┐
                          │  前端（独立仓库）        │
                          └───────────┬───────────┘
                                      │ /admin-api/**、/app-api/**
                          ┌───────────▼───────────┐        ┌─────────────────┐
                          │   gateway-server       │◄──────►│  Nacos 3.x       │
                          │   :48080               │  服务发现 │  注册中心 + 配置中心 │
                          └───────────┬───────────┘        └────────┬────────┘
                                      │ grayLb://<服务名>             │
        ┌──────────────┬──────────────┼──────────────┬──────────────┘
        ▼              ▼              ▼              ▼
┌──────────────┐┌──────────────┐┌──────────────┐┌──────────────┐
│ system-server││ infra-server ││ bpm-server   ││ 其他业务服务   │
│   :48081     ││   :48082     ││   :48083     ││ 48084 ~ 48103│
└──────┬───────┘└──────┬───────┘└──────┬───────┘└──────┬───────┘
       │               │               │               │
       └───────────────┴───────┬───────┴───────────────┘
                               ▼
        ┌──────────────────────────────────────────────┐
        │ MySQL · Redis · MQ · XXL-Job · Elasticsearch  │
        └──────────────────────────────────────────────┘
```

请求链路：

1. 浏览器访问网关（或经 Nginx 反向代理到网关），路径前缀为 `/admin-api/**`（管理后台）或 `/app-api/**`（用户端）。
2. 网关按路径前缀路由到对应服务，例如 `/admin-api/system/**` → `system-server`。
3. 服务启动时注册到 Nacos；网关通过 `grayLb://服务名` 从 Nacos 获取实例并做负载均衡（支持 `metadata.version` 灰度）。
4. 服务之间通过 Feign RPC 调用（`full-spring-boot-starter-rpc`），跨服务事务可使用 Seata（可选）。

### 2.2 工程结构

```text
full-cloud
├── full-dependencies          # Maven BOM，统一管理所有依赖版本
├── full-framework             # 框架组件（不包含业务）
│   ├── full-common
│   ├── full-spring-boot-starter-env          # 环境标识、灰度标签
│   ├── full-spring-boot-starter-mybatis      # MyBatis-Plus、多数据源
│   ├── full-spring-boot-starter-redis        # Redis、Redisson
│   ├── full-spring-boot-starter-web          # Web、全局异常、Swagger
│   ├── full-spring-boot-starter-security     # 认证鉴权
│   ├── full-spring-boot-starter-websocket
│   ├── full-spring-boot-starter-monitor      # Actuator、Spring Boot Admin
│   ├── full-spring-boot-starter-protection   # 限流、幂等、分布式锁
│   ├── full-spring-boot-starter-job          # XXL-Job
│   ├── full-spring-boot-starter-mq           # RocketMQ / RabbitMQ / Kafka
│   ├── full-spring-boot-starter-rpc          # Feign、灰度负载均衡
│   ├── full-spring-boot-starter-excel
│   ├── full-spring-boot-starter-biz-tenant   # 多租户
│   ├── full-spring-boot-starter-biz-data-permission
│   ├── full-spring-boot-starter-biz-ip
│   └── full-spring-boot-starter-elasticsearch
├── full-gateway               # 网关服务（启动类 GatewayServerApplication）
├── full-module-*              # 业务模块，每个模块拆分为 api + server
│   ├── full-module-xxx-api    # 对外 RPC 接口、DTO、枚举，供其他服务依赖
│   └── full-module-xxx-server # 业务实现、Controller、Mapper，可独立启动
├── script
│   ├── docker-compose         # Docker Compose 入门部署编排
│   ├── jenkins                # Jenkins 单服务部署流水线
│   ├── seata                  # Seata 接入示例与说明
│   ├── sentinel               # Sentinel 规则与示例
│   └── sharding               # 分库分表示例
├── sql                        # 各数据库初始化脚本（mysql、postgresql、oracle 等）
│   └── sync                   # SQL 脚本同步管理工具（见 sql/sync/README.md）
└── pom.xml
```

约定：

- `full-module-xxx-api` 只放接口与模型，被其他业务模块依赖；`full-module-xxx-server` 依赖本模块 api，打包为可执行 Jar。
- 跨模块调用只依赖对方的 `-api`，不直接依赖对方的 `-server`。
- 通用能力放 `full-framework`，业务模块不重复实现。

### 2.3 业务模块与默认端口

| 模块 | 服务名 | 端口 | 说明 |
| --- | --- | --- | --- |
| full-gateway | gateway-server | 48080 | 统一入口、路由、Swagger 聚合 |
| full-module-system | system-server | 48081 | 用户、角色、菜单、字典、登录认证 |
| full-module-infra | infra-server | 48082 | 代码生成、文件、日志、配置、监控 |
| full-module-bpm | bpm-server | 48083 | 工作流（Flowable） |
| full-module-report | report-server | 48084 | 报表（积木报表、UReport） |
| full-module-pay | pay-server | 48085 | 支付、退款、转账 |
| full-module-mp | mp-server | 48086 | 微信公众号、小程序 |
| full-module-member | member-server | 48087 | 会员中心 |
| full-module-erp | erp-server | 48088 | ERP |
| full-module-crm | crm-server | 48089 | CRM |
| full-module-ai | ai-server | 48090 | AI 对话、绘画、知识库、MCP |
| full-module-iot | iot-server | 48091 | 物联网平台 |
| full-module-mes | mes-server | 48091 | MES（默认端口与 iot-server 相同，同时启动需修改其一） |
| full-module-wms | wms-server | 48092 | WMS |
| full-module-im | im-server | 48093 | 即时通讯 |
| full-module-hrm | hrm-server | 48094 | 人力资源 |
| full-module-fms | fms-server | 48095 | 财务管理 |
| full-module-pms | pms-server | 48096 | 项目管理 |
| full-module-oa | oa-server | 48097 | OA |
| full-module-mall/product | product-server | 48100 | 商品 |
| full-module-mall/promotion | promotion-server | 48101 | 营销 |
| full-module-mall/trade | trade-server | 48102 | 交易 |
| full-module-mall/statistics | statistics-server | 48103 | 统计 |
| full-module-iot-gateway | iot-gateway-server | 8090~8094 等 | IoT 设备接入网关（HTTP/MQTT/CoAP/Modbus 等协议端口见其 `application.yaml`） |

端口以各模块 `src/main/resources/application.yaml` 中的 `server.port` 为准。

### 2.4 配置加载机制

每个服务启动时按以下顺序加载配置，后者覆盖前者：

1. Jar 内 `application.yaml`
2. Jar 内 `application-${spring.profiles.active}.yaml`（默认 `local`）
3. Nacos 配置中心 Data ID：`${spring.application.name}-${spring.profiles.active}.yaml`（可选，不存在则忽略）
4. 启动时的环境变量 / 命令行参数

因此数据库、Redis、Nacos 等敏感配置既可以在本地 `application-local.yaml` 中修改，也可以放到 Nacos 或环境变量中。

## 三、启动指南

### 3.1 环境准备

| 依赖 | 要求 | 说明 |
| --- | --- | --- |
| JDK | 25 | `java -version` 校验 |
| Maven | 3.8+ | 项目根目录已配置华为云、阿里云镜像 |
| MySQL | 8.x | 默认库名 `ruoyi-vue-pro`，账号 `root/123456` |
| Redis | 7.x | 默认 `127.0.0.1:6379`，`database=0` |
| Nacos | 3.x | 默认 `127.0.0.1:8848`，需创建命名空间 `dev` |

可选组件（按需启用）：

- XXL-Job：本地配置默认 `xxl.job.enabled=false`，需要定时任务时再启动调度中心
- RocketMQ / RabbitMQ / Kafka、Elasticsearch、Seata、Sentinel：仅相关模块使用，本地联调时可暂不启动
- IoT 设备网关：需要设备接入时单独启动 `iot-gateway-server`

### 3.2 初始化数据库

1. 创建数据库 `ruoyi-vue-pro`（字符集 `utf8mb4`）。
2. 依次导入：

```text
sql/mysql/ruoyi-vue-pro.sql   # 业务表 + 初始化数据
sql/mysql/quartz.sql          # Quartz 定时任务表
```

其他数据库（PostgreSQL、Oracle、SQL Server、DM、Kingbase、OpenGauss、OceanBase 等）使用 `sql/` 下对应目录的脚本。

### 3.3 修改本地配置

本地配置位于各服务 `src/main/resources/application-local.yaml`，至少确认以下三项：

- `spring.cloud.nacos.server-addr`、`discovery.namespace`、`config.namespace`（默认 `127.0.0.1:8848`、`dev`）
- `spring.datasource.dynamic.datasource.master/slave` 的 URL、用户名、密码（默认 `jdbc:mysql://127.0.0.1:3306/ruoyi-vue-pro`，`root/123456`）
- `spring.data.redis.host/port/database`（默认 `127.0.0.1:6379`、`0`）

同时需要在 Nacos 控制台创建命名空间 `dev`（命名空间 ID 填 `dev`），否则服务无法完成注册与配置拉取。

### 3.4 编译项目

在项目根目录执行：

```shell
mvn clean install -Dmaven.test.skip=true
```

只想编译某个服务及其依赖时：

```shell
mvn clean package -pl full-module-system/full-module-system-server -am -Dmaven.test.skip=true
```

### 3.5 启动服务

启动顺序建议为：Nacos → MySQL / Redis → `infra-server` → `system-server` → `gateway-server` → 其他业务服务。

方式一：IDE 运行各服务启动类

| 服务 | 启动类 |
| --- | --- |
| 网关 | `cn.full.cloud.gateway.GatewayServerApplication` |
| 系统 | `cn.full.cloud.module.system.SystemServerApplication` |
| 基础设施 | `cn.full.cloud.module.infra.InfraServerApplication` |
| 其他模块 | `full-module-xxx/full-module-xxx-server` 下的 `XxxServerApplication` |

方式二：命令行运行 Jar

```shell
java -jar full-gateway/target/full-gateway.jar
java -jar full-module-system/full-module-system-server/target/full-module-system-server.jar
java -jar full-module-infra/full-module-infra-server/target/full-module-infra-server.jar
```

如需切换环境，追加 `--spring.profiles.active=dev` 或设置环境变量 `SPRING_PROFILES_ACTIVE=dev`。

### 3.6 验证启动结果

- 各服务日志出现 `Started XxxServerApplication`
- Nacos 控制台「服务管理 → 服务列表」中能看到 `gateway-server`、`system-server` 等实例
- 网关聚合接口文档：<http://127.0.0.1:48080/doc.html>
- 单个服务接口文档：`http://127.0.0.1:<端口>/swagger-ui`
- 管理后台前端（独立仓库）将 API 地址指向 `http://127.0.0.1:48080` 或经 Nginx 代理的同源地址

常见问题：

- 启动报 Nacos 连接失败：确认 Nacos 已启动、8848 与 9848（gRPC）端口可访问、命名空间 `dev` 已创建。
- 网关返回 503：服务尚未注册到 Nacos 或注册到了不可达的 IP，稍等重试并检查 Nacos 实例列表。
- 数据库连接失败：确认库已创建、SQL 已导入、`application-local.yaml` 中账号密码正确。

## 四、部署指南

### 4.1 打包

```shell
# 全量打包
mvn clean package -Dmaven.test.skip=true

# 只打包需要部署的服务（推荐）
mvn clean package -pl full-gateway,full-module-system/full-module-system-server,full-module-infra/full-module-infra-server -am -Dmaven.test.skip=true
```

产物位于各模块 `target/` 目录，例如 `full-gateway/target/full-gateway.jar`。各 `-server` 模块与 `full-gateway` 均自带 `Dockerfile`（基础镜像 `eclipse-temurin:25-jre`，默认 `-Xms512m -Xmx512m`），可直接用于构建镜像。

### 4.2 Docker Compose 部署（入门体验）

编排文件位于 [script/docker-compose](script/docker-compose)，包含 `gateway + system-server + infra-server + Nginx + MySQL + Redis + 可选内置 Nacos`，详细说明见 [script/docker-compose/README.md](script/docker-compose/README.md)。

简要步骤：

```shell
# 1. 源码根目录打包后端
mvn clean package -pl full-gateway,full-module-system/full-module-system-server,full-module-infra/full-module-infra-server -am -Dmaven.test.skip=true

# 2. 准备前端产物（独立仓库打包结果，包含 index.html）
mkdir -p script/docker-compose/web/dist
cp -R /path/to/前端打包产物/. script/docker-compose/web/dist/

# 3. 配置环境变量，至少替换数据库、Redis、Nacos 的示例密码
cd script/docker-compose
cp .env.example .env

# 4. 构建并启动
docker compose up -d --build

# 5. 查看状态与日志
docker compose ps
docker compose logs -f gateway system-server infra-server
```

访问 `http://localhost:8080`（`WEB_PORT` 可调整）。注意事项：

- 前端 API 地址必须使用同源路径 `/admin-api`，不能写容器名或 `127.0.0.1:48080`
- 内置 Nacos 仅用于本机体验；复用已有 Nacos 时清空 `COMPOSE_PROFILES`，并把 `NACOS_SERVER_ADDR` 改为容器内可访问的地址
- `docker compose down` 保留数据卷；不要执行 `docker compose down -v`，否则 MySQL、Redis、Nacos 数据会全部丢失
- SQL 只在首次启动（数据卷为空）时自动导入

### 4.3 Jenkins 部署（单服务发布）

流水线文件为 [script/jenkins/Jenkinsfile](script/jenkins/Jenkinsfile)，按「一个服务一个 Pipeline Job」使用：

1. 创建 Pipeline 类型的 Job，Job 名称必须是服务名（如 `gateway-server`、`system-server`、`infra-server`），选择「Pipeline script from SCM」，Script Path 填 `script/jenkins/Jenkinsfile`。
2. Jenkins 全局 Tools 中配置 `jdk25`、`maven3`；创建 SSH 私钥凭据 `yudao-deploy-ssh` 和 known_hosts 凭据 `yudao-deploy-known-hosts`。
3. 目标服务器创建 `<DEPLOY_BASE_DIR>/<服务名>` 目录，并放入 `app.env`（数据库、Redis、Nacos 地址与密码，建议 `chmod 600`）。
4. 构建参数填写 `DEPLOY_HOST`、`DEPLOY_USER`、`DEPLOY_SSH_PORT`、`DEPLOY_BASE_DIR`。

流水线会依次执行：拉取代码 → Maven 打包 → 上传 Jar → 备份旧包 → 停止旧进程 → 替换 → 启动并探活。启动失败时日志会打印备份路径，可人工回滚到 `backup/` 下的旧 Jar。

### 4.4 手动部署（Linux 服务器）

```shell
# 服务器目录规划
mkdir -p /work/projects/system-server
cd /work/projects/system-server

# 上传 Jar 与运行时配置 app.env（内容示例）
# SPRING_PROFILES_ACTIVE=prod
# SERVER_PORT=48081
# SPRING_CLOUD_NACOS_SERVER_ADDR=10.0.0.10:8848
# SPRING_DATASOURCE_DYNAMIC_DATASOURCE_MASTER_URL=jdbc:mysql://10.0.0.11:3306/ruoyi-vue-pro?...
# SPRING_DATASOURCE_DYNAMIC_DATASOURCE_MASTER_USERNAME=...
# SPRING_DATASOURCE_DYNAMIC_DATASOURCE_MASTER_PASSWORD=...

# 启动
set -a; . ./app.env; set +a
nohup java -Xms512m -Xmx512m -jar full-module-system-server.jar > nohup.out 2>&1 &
```

网关与其他服务同理，按服务名分目录部署即可。

### 4.5 生产环境建议

- 配置外置：数据库、Redis、Nacos 的地址与密码通过环境变量或 Nacos Data ID（`${spring.application.name}-prod.yaml`）注入，不要把生产密码提交到仓库。
- 注册中心隔离：生产使用独立的 Nacos 命名空间或分组，避免与测试、IDE 本地服务互相发现。
- 网关前置 Nginx：由 Nginx 负责 HTTPS、静态资源、`/admin-api`、`/app-api`、`/infra/ws` 反向代理（参考 [script/docker-compose/nginx/default.conf](script/docker-compose/nginx/default.conf)）。
- JVM 与日志：按服务调整堆内存；日志默认写入 `${user.home}/logs/<服务名>.log`，建议接入日志采集。
- 监控：按需启用 Actuator、Spring Boot Admin、SkyWalking/OpenTelemetry、Sentinel 规则持久化。
- 数据库：上线前备份，版本升级时手动执行对应升级 SQL；`sql/` 下按数据库类型提供独立脚本。
- 灰度发布：网关使用 `grayLb://` 负载均衡，可通过 Nacos 实例 `metadata.version` 控制流量版本。
