# Docker Compose 部署（微服务版）

目标：在服务器上用 Docker Compose 部署 `gateway`、`system-server`、`infra-server`，复用服务器上已有 Nacos、MySQL、Redis 和宿主机 Nginx。本编排不启动任何内置中间件，也不包含容器 Nginx。

## 文件列表

```text
script/docker-compose
├── README.md
├── docker-compose.yml       <-- 编排文件，相对路径均相对于本目录
├── Dockerfile               <-- 通用 Java 服务镜像，按 JAR_FILE 构建
├── .env.example             <-- 环境变量示例，复制为 .env 后修改
├── .gitignore               <-- 忽略 .env、web/dist
├── gateway-server
│   └── full-gateway.jar
├── system-server
│   └── full-module-system-server.jar
├── infra-server
│   └── full-module-infra-server.jar
└── nginx
    └── default.conf         <-- 宿主机 Nginx 反向代理参考
```

服务器上只需要这个目录和三个服务目录里的 jar，不需要 `full-gateway`、`full-module-*-server` 等源码目录，也不需要 `target` 目录。

`web/` 目录不再被本编排使用，前端静态资源由宿主机 Nginx 直接提供。

## 服务

| 服务 | 镜像 | 说明 |
| --- | --- | --- |
| `gateway` | `full-gateway:${IMAGE_TAG}` | 由同目录 Dockerfile + `gateway-server/full-gateway.jar` 构建，端口 48080，Nacos 服务名 `gateway-server` |
| `system-server` | `full-module-system-server:${IMAGE_TAG}` | 由同目录 Dockerfile + `system-server/full-module-system-server.jar` 构建，端口 48081，Nacos 服务名 `system-server` |
| `infra-server` | `full-module-infra-server:${IMAGE_TAG}` | 由同目录 Dockerfile + `infra-server/full-module-infra-server.jar` 构建，端口 48082，Nacos 服务名 `infra-server` |

请求链路：浏览器 → 宿主机 Nginx → `gateway`（`127.0.0.1:${GATEWAY_PORT}`）→ 通过 Nacos 发现 `system-server`、`infra-server`。

三个 Java 服务都接入 `SHARED_NETWORK`（默认 `baota_net`），直接用容器别名访问 `nacos:8848`、`mysql:3306`、`redis:6379`。

## 内存要求与 JVM 参数

三个服务都是 JVM 进程，除堆内存外还要占用元空间、代码缓存、直接内存和线程栈。旧的默认值 `-Xms512m -Xmx512m` 会让三个进程在启动时就提交 1.5G 堆内存，加上非堆内存后超过 2G；在只剩约 2G 可用内存的服务器上会触发宿主机 OOM，表现为服务器卡死、SSH 断开。

本编排默认按小内存服务器收紧如下（可在 `.env` 覆盖）：

| 服务 | 堆内存 | 元空间 / 代码缓存 / 直接内存上限 | 容器内存上限 |
| --- | --- | --- | --- |
| `gateway` | 128m ~ 256m | 160m / 48m / 96m | 512m |
| `system-server` | 192m ~ 320m | 192m / 64m / 96m | 640m |
| `infra-server` | 192m ~ 320m | 192m / 64m / 96m | 640m |

三个容器合计上限约 1.75G，正常运行时约 1.1G ~ 1.5G（本地实测网关空载常驻内存约 200m）。统一附加的参数：

- `-XX:ActiveProcessorCount=2`：不按宿主机全部 CPU 核数创建 GC、Netty 和线程池线程，减少线程栈占用
- `-XX:+UseSerialGC`：小堆下比 G1 占用更少的线程和 native 内存
- `-XX:+ExitOnOutOfMemoryError`：内存溢出时直接退出并由 `restart` 策略重启，避免进程半死不活
- `memswap_limit` 与 `mem_limit` 相同：容器不占用 swap，内存超限时只杀容器，不会把宿主机拖入 swap 假死

内存充足（例如服务器可用内存 6G 以上）时，再通过 `.env` 调整：

```ini
GATEWAY_JAVA_OPTS=-Xms256m -Xmx512m -XX:MaxMetaspaceSize=192m -XX:ReservedCodeCacheSize=64m -XX:MaxDirectMemorySize=128m -Xss512k -XX:ActiveProcessorCount=4
GATEWAY_MEM_LIMIT=1280m
APP_JAVA_OPTS=-Xms512m -Xmx768m -XX:MaxMetaspaceSize=256m -XX:ReservedCodeCacheSize=64m -XX:MaxDirectMemorySize=128m -Xss512k -XX:ActiveProcessorCount=4
APP_MEM_LIMIT=1536m
```

`mem_limit` 必须大于“堆 + 非堆 + 线程栈”的总和，否则容器会先被 Docker OOM Kill。排查命令：

```shell
docker stats --no-stream
docker inspect -f '{{.Name}} OOMKilled={{.State.OOMKilled}} Exit={{.State.ExitCode}}' $(docker compose ps -q)
docker compose logs --tail=200 gateway system-server infra-server
```

服务器内存紧张时，建议按 `gateway` → `system-server` → `infra-server` 顺序逐个启动，避免三个 JVM 同时做类加载和 JIT 编译：

```shell
docker compose up -d --build gateway
docker compose up -d system-server
docker compose up -d infra-server
```

## 前置条件

- Docker Engine + Docker Compose V2（`docker compose version` 可查看）
- 已部署 Nacos、MySQL、Redis，并且它们都在 `SHARED_NETWORK`（默认 `baota_net`）里，网络别名为 `nacos`、`mysql`、`redis`
- 宿主机已安装 Nginx
- JDK 25、Maven（在服务器上构建 jar 时需要，与源码根 `pom.xml` 的 `java.version` 一致）
- 已准备好前端打包产物，供宿主机 Nginx 使用

## 1. 打包后端

在源码根目录执行：

```shell
mvn clean package -pl full-gateway,full-module-system/full-module-system-server,full-module-infra/full-module-infra-server -am -Dmaven.test.skip=true
```

`target` 下会生成三个 jar，复制到本目录对应的服务目录，文件名必须保持一致：

```shell
mkdir -p script/docker-compose/gateway-server script/docker-compose/system-server script/docker-compose/infra-server
cp full-gateway/target/full-gateway.jar script/docker-compose/gateway-server/
cp full-module-system/full-module-system-server/target/full-module-system-server.jar script/docker-compose/system-server/
cp full-module-infra/full-module-infra-server/target/full-module-infra-server.jar script/docker-compose/infra-server/
```

`docker-compose.yml` 使用同目录 `Dockerfile`，通过 `JAR_FILE` 构建参数把对应服务目录下的 jar 打进镜像，所以服务器上不需要模块源码目录和 `target` 目录。

## 2. 准备外部中间件

### MySQL

MySQL 容器已初始化过时，`MYSQL_DATABASE`、`MYSQL_USER` 等初始化变量不会再生效，需要手动建库、建账号并导入 SQL。基础编排只部署 system、infra，导入 `sql/mysql/ruoyi-vue-pro.sql` 即可；部署其他模块时，再导入 `sql/mysql/<模块>/` 下对应的 SQL。

```shell
docker exec -i mysql-mysql-1 sh -c 'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD"' <<'SQL'
CREATE DATABASE IF NOT EXISTS `ruoyi-vue-pro` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'yudao'@'%' IDENTIFIED BY '你的业务账号密码';
GRANT ALL PRIVILEGES ON `ruoyi-vue-pro`.* TO 'yudao'@'%';
FLUSH PRIVILEGES;
SQL
```

```shell
docker exec -i mysql-mysql-1 sh -c 'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" ruoyi-vue-pro' < sql/mysql/ruoyi-vue-pro.sql
```

SQL 文件包含 `DROP TABLE IF EXISTS`，只能对空的 `ruoyi-vue-pro` 库执行。

### Redis

项目各服务默认使用 `REDIS_DATABASE=1`，确认该库未被其他应用占用，或修改 `.env` 中的库号。

### Nacos

- `NACOS_SERVER_ADDR=nacos:8848`，客户端同时使用 HTTP 8848 和 gRPC 9848。
- 本分支 `nacos-client` 为 3.1.1，服务端 Nacos 2.4.2 的基础注册/配置通常兼容；若注册异常，优先升级 Nacos 3.x。
- 开启鉴权时填写 `NACOS_USERNAME`、`NACOS_PASSWORD`。
- `NACOS_NAMESPACE` 填控制台命名空间的 **ID**，不是名称。

## 3. 配置环境变量

```shell
cd script/docker-compose
cp .env.example .env
```

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `SHARED_NETWORK` | `baota_net` | 应用容器接入的中间件网络名 |
| `GATEWAY_PORT` | `48080` | 宿主机 Nginx 反向代理网关的端口，只绑定 `127.0.0.1` |
| `IMAGE_TAG` | `local` | 后端镜像 tag |
| `MYSQL_HOST` / `MYSQL_PORT` | `mysql` / `3306` | MySQL 地址与端口（容器网络内） |
| `MYSQL_DATABASE` | `ruoyi-vue-pro` | 数据库名 |
| `MYSQL_USER` / `MYSQL_PASSWORD` | `yudao` / 示例值 | 应用使用的数据库账号 |
| `REDIS_HOST` / `REDIS_PORT` | `redis` / `6379` | Redis 地址与端口（容器网络内） |
| `REDIS_DATABASE` | `1` | Redis 数据库索引 |
| `REDIS_PASSWORD` | 示例值 | Redis 密码 |
| `SPRING_PROFILES_ACTIVE` | `dev` | 后端 profile，同时决定 Nacos Data ID 后缀 |
| `GATEWAY_JAVA_OPTS` | 见「内存要求与 JVM 参数」 | 网关 JVM 参数 |
| `GATEWAY_MEM_LIMIT` | `512m` | 网关容器内存上限 |
| `APP_JAVA_OPTS` | 见「内存要求与 JVM 参数」 | `system-server`、`infra-server` 共用的 JVM 参数 |
| `APP_MEM_LIMIT` | `640m` | `system-server`、`infra-server` 各自的容器内存上限 |
| `FULL_CAPTCHA_ENABLE` | `true` | 是否开启登录验证码 |
| `NACOS_SERVER_ADDR` | `nacos:8848` | Nacos 地址，必须是**容器内**可访问的地址 |
| `NACOS_NAMESPACE` | `public` | 命名空间 ID，注册中心与配置中心共用 |
| `NACOS_GROUP` | `DEFAULT_GROUP` | 分组，注册中心与配置中心共用 |
| `NACOS_USERNAME` / `NACOS_PASSWORD` | 空 | Nacos 开启鉴权时填写 |

> 旧版 `.env` 中的 `JAVA_OPTS` 已不再使用，保留也不影响；升级后直接使用上面的默认值。

## 4. 启动

以下命令均在 `script/docker-compose` 目录执行：

```shell
# 检查配置（变量缺失会直接报错）
docker compose config

# 构建后端镜像并启动
docker compose up -d --build

# 查看状态与日志
docker compose ps
docker compose logs -f gateway system-server infra-server
```

如果服务器可用内存接近 2G，优先使用上文「内存要求与 JVM 参数」中的逐个启动命令，等前一个服务启动完成、内存稳定后再启动下一个。

三个服务日志分别出现 `Started GatewayServerApplication`、`Started SystemServerApplication`、`Started InfraServerApplication`，并在 Nacos 中注册后，即可通过宿主机 Nginx 访问。

服务刚启动时网关可能短暂返回 503（尚未从 Nacos 拉取到实例），稍等后刷新即可。

## 5. 宿主机 Nginx

`nginx/default.conf` 是反向代理参考，用于宿主机 Nginx 时需要调整：

- 把 `resolver 127.0.0.11` 和 `set $yudao_backend http://gateway:48080` 去掉，改成 `proxy_pass http://127.0.0.1:48080;`（端口与 `GATEWAY_PORT` 一致）
- `map $http_upgrade $connection_upgrade` 必须放在 http 级（`nginx.conf` 或 http 级 include 文件），不能放在 server 块里
- 前端静态资源目录、域名、HTTPS 证书按宿主机实际情况配置
- 保留 `/admin-api`、`/app-api`、`/infra/ws` 的代理规则和 `client_max_body_size 32m`

## 6. 更新

```shell
# 后端：回到源码根目录重新打包，复制新 jar 后重建、重启
cd ../..
mvn clean package -pl full-gateway,full-module-system/full-module-system-server,full-module-infra/full-module-infra-server -am -Dmaven.test.skip=true
cp full-gateway/target/full-gateway.jar script/docker-compose/gateway-server/
cp full-module-system/full-module-system-server/target/full-module-system-server.jar script/docker-compose/system-server/
cp full-module-infra/full-module-infra-server/target/full-module-infra-server.jar script/docker-compose/infra-server/
cd script/docker-compose
docker compose up -d --build gateway system-server infra-server
```

如需回滚，可在打包前修改 `.env` 的 `IMAGE_TAG`，保留旧 tag 的镜像。

## 7. 停止

```shell
docker compose down
```

MySQL、Redis、Nacos 的数据都在外部容器中，本编排不创建数据卷，`docker compose down` 不会影响业务数据。

## 8. 后续新增服务或文件

三个原则：

- 不要长期在容器里直接改文件，容器重建后改动会丢失。
- 只重建受影响的服务，不要 `docker compose down` 整个项目；`docker compose up -d --build <服务名>` 只重建指定服务。
- 每次修改 `docker-compose.yml` 或 `.env` 后，先执行 `docker compose config` 检查。

### 8.1 给现有服务增加配置文件

文件需要持久生效时，用 bind mount 挂载到宿主机目录：

1. 在宿主机对应服务目录下放文件，例如：

   ```text
   /work/full-cloud/system-server/config/application-extra.yaml
   ```

2. 在 `docker-compose.yml` 的对应服务下增加挂载：

   ```yaml
   system-server:
     volumes:
       - ./system-server/config/application-extra.yaml:/app/config/application-extra.yaml:ro
   ```

3. 让应用读取该文件，例如在服务 `environment` 中增加：

   ```yaml
   SPRING_CONFIG_ADDITIONAL_LOCATION: file:/app/config/application-extra.yaml
   ```

4. 只重建该服务：

   ```shell
   docker compose up -d system-server
   ```

5. 查看日志确认配置已加载：

   ```shell
   docker compose logs -f system-server
   ```

如果文件必须打进镜像（例如证书、启动脚本），推荐给该服务单独写一个 Dockerfile 并在 compose 中指定 `build.dockerfile`；不要用 `docker cp` 作为长期方案，容器重建后文件会丢失。

### 8.2 新增一个 Java 服务（以 bpm-server 为例）

1. 打包并生成 jar：

   ```shell
   mvn clean package -pl full-module-bpm/full-module-bpm-server -am -Dmaven.test.skip=true
   ```

2. 上传到宿主机新目录，目录名与 compose 中的路径一致：

   ```text
   /work/full-cloud/bpm-server/full-module-bpm-server.jar
   ```

3. 在 `docker-compose.yml` 增加服务块：

   ```yaml
   bpm-server:
     build:
       context: .
       dockerfile: Dockerfile
       args:
         JAR_FILE: bpm-server/full-module-bpm-server.jar
         APP_PORT: "48083" # 以模块 application.yaml 的 server.port 为准
     image: full-module-bpm-server:${IMAGE_TAG:-local}
     restart: unless-stopped
     networks:
       - baota_net
     environment:
       <<: *app-env
     mem_limit: ${APP_MEM_LIMIT:-640m}
     memswap_limit: ${APP_MEM_LIMIT:-640m}
   ```

   - 需要 MySQL、Redis 的模块用 `*app-env`，会自动带上小内存 JVM 参数。
   - 只需要 Nacos 注册/配置的模块可以用 `*common-env`；这种服务不会继承 `APP_JAVA_OPTS`，使用镜像内默认 JVM 参数，`mem_limit` 仍要按同样方式加上。
   - 如果模块需要额外的环境变量，在 `.env` 中定义后加到该服务的 `environment`。
   - 新增服务后请重新核算总内存，所有 `mem_limit` 之和不要超过服务器可用内存的 80%。

4. 如果模块有独立 SQL，先导入 `sql/mysql/<模块>/` 下对应脚本。

5. 校验并只启动新服务：

   ```shell
   docker compose config
   docker compose up -d --build bpm-server
   docker compose logs -f bpm-server
   ```

6. 确认 Nacos 中出现了新服务实例。

7. 网关路由：`full-gateway/src/main/resources/application.yaml` 已包含 bpm 的 `/admin-api/bpm/**` 路由。如果新增模块没有对应路由，需要先在 gateway 的应用配置里补上，再重建网关：

   ```shell
   docker compose up -d --build gateway
   ```

### 8.3 给已有服务更新 jar

1. 覆盖对应服务目录下的 jar，例如：

   ```shell
   cp full-gateway/target/full-gateway.jar /work/full-cloud/gateway-server/
   ```

2. 只重建该服务：

   ```shell
   cd /work/full-cloud
   docker compose up -d --build gateway
   ```

3. 需要回滚时，在覆盖前备份旧 jar，或用不同的 `IMAGE_TAG` 保留旧镜像。

### 8.4 临时文件（不推荐长期使用）

只用于临时排查时，可以用：

```shell
docker cp ./some-file <容器名>:/app/
```

容器重建后文件会丢失，正式方案仍然是 bind mount 或重建镜像。

### 8.5 新增环境变量

1. 在 `.env` 中增加变量。
2. 在对应服务的 `environment` 中引用，例如：

   ```yaml
   environment:
     MY_VAR: ${MY_VAR}
   ```

3. 只重建对应服务：

   ```shell
   docker compose up -d <服务名>
   ```

`.env` 包含密码，不要提交到仓库，也不要放进 Nginx 站点目录。
