# udpxy-scanner 完整功能流程

## 一、系统架构

### 数据库（1 库 5 表）

| 数据库 | 表 | 用途 |
|--------|-----|------|
| `data.db` | `parameter` | 参数管理（并发数、超时、cron、推送 API Key、密码） |
| | `config` | 扫描配置（名称、数据源、模板地区/运营商/频道/地址、启用状态） |
| | `subscription` | API 订阅（名称、uid、URL、cron、启用状态） |
| | `cache` | host 缓存池（host 唯一，sourceType 记录首次发现来源, geoRegion, geoOperator） |
| | `host` | 活源池（host+target+channelName 唯一约束） |

### 核心模块

| 模块 | 职责 |
|------|------|
| `core/engine.py` | 扫描引擎：从 source_cache 过滤候选 → 验证 → 写入 hosts |
| `core/status.py` | 任务状态：扫描/复测的启停、进度、队列管理 |
| `services/geoip.py` | GeoIP 服务：health_check + ip2region 地理位置查询 + 内网/国外过滤 |
| `services/validator.py` | 流验证：GET /{proto}/{target} → 读 512B → 判定有效 |
| `services/source_cache.py` | 缓存读写：source_cache 的 CRUD + geo 批量操作 + 去重 |
| `services/regions.py` | 公共常量：中国内地省级行政区集合 |
| `services/cron_heartbeat.py` | 定时调度：扫描/复测/订阅拉取的 cron 匹配与触发 |
| `services/subscription_fetcher.py` | 订阅拉取：从外部 API 获取 host 列表 |
| `services/log_buffer.py` | 日志缓冲：内存环形缓冲，前端实时查看 |
| `db/database.py` | 数据层：连接池（threading.local 持久连接）、设置缓存、run_in_thread |

---

## 二、流程 A：数据源 → source_cache（"蓄水池"）

### 目的
将外部发现的 host 经过有效性验证和 geo 富化后，缓存到 source_cache 中，供扫描引擎按地区筛选使用。

### 触发入口（3 种）

| 入口 | 触发方式 | 认证 | 执行方式 |
|------|----------|------|----------|
| `POST /api/source/push` | CI 扫描器（ZoomEye/GitHub Code Search）主动推送 | X-API-Key | 后台异步（create_task） |
| `POST /api/subscriptions/{id}/fetch` | 用户手动点击 | 登录 Token | 后台线程 |
| `POST /api/cron/heartbeat` | 外部 crontab 每分钟调用 | 无需认证 | 同步 + 并发 |

### 详细流程

```
外部推送/订阅拉取/cron定时
        │
        │  输入: sourceType=订阅uid, hosts=[{host, geoRegion?, geoOperator?}]
        │
        ▼
  process_source_data(source_type, hosts)          ← source_cache.py
        │
        ▼
  enrich_geo_batch(hosts)                          ← geoip.py
   │
   │  ① health_check (GET http://{host}/status)
   │     ├─ 返回 200 + body 含 "udpxy status" → 有效，继续
   │     └─ 其他 → 无效，过滤掉
   │
   │  ② 已有 geoRegion/geoOperator → 直接保留（跳过查询）
   │
   │  ③ 查 source_cache 缓存 (get_cached_geo_batch)
   │     └─ 命中 → 补充 geo 信息
   │
   │  ④ DNS 解析 host → IP
   │     └─ 解析失败 → geoRegion="" → 后续被 cache_sources 过滤
   │
   │  ⑤ ip2region 查询 IP
   │     ├─ 私有/内网/回环 IP (is_private/is_loopback/is_link_local) → is_foreign=True → 丢弃
   │     ├─ 国外 IP (countryCode != CN) → is_foreign=True → 丢弃
   │     ├─ 非大陆 IP (港澳台，不在 MAINLAND_REGIONS) → is_foreign=True → 丢弃
   │     └─ 中国内地 → 返回 {region, operator, countryCode=CN}
   │
   ▼
  cache_sources(source_type, enriched)             ← source_cache.py
   │
   ├─ 按 host 去重
   ├─ geoRegion 为空 或 不在 MAINLAND_REGIONS → 丢弃（隐式兜底过滤内网/DNS失败）
   └─ INSERT OR IGNORE INTO source_cache
       (sourceType=订阅uid, host, geoRegion, geoOperator)
```

### 关键点
- **source_cache 按 (host) 唯一索引**，同一 host 只有一条记录，sourceType 记录首次发现该 host 的来源（先到先得，后到跳过）
- **health_check 只在推送/订阅拉取路径做**，扫描引擎路径跳过（因为 verify_single_host 已验证）
- **三层过滤**：① 显式私有IP过滤 → ② ip2region 国外/非大陆过滤 → ③ cache_sources 空 region 兜底过滤

---

## 三、流程 B：扫描配置 → source_cache 过滤 → 验证 → hosts（"活源池"）

### 目的
根据扫描配置的地区条件，从 source_cache 中筛选候选 host，验证流可用性，有效源写入活源池。

### 触发入口

| 入口 | 触发方式 |
|------|----------|
| `POST /api/configs/{id}/run` | 用户手动启动单个配置 |
| `POST /api/configs/run-all` | 用户手动启动所有启用配置 |
| `POST /api/cron/heartbeat` | cron 定时匹配 scan_cron |

### 核心概念：templateRegion

`templateRegion` 是扫描配置中的**地区筛选条件**。扫描引擎用它从 source_cache 中 `WHERE geoRegion = templateRegion` 过滤出指定地区的 host。

例如：templateRegion="北京" → 只取 source_cache 中 geoRegion="北京" 的 host 进行验证。

### 详细流程（以扫描北京主机为例）

```
用户操作: 创建扫描配置
  name = "北京主机"
  templateRegion = "北京"              ← 地区筛选条件
  templateOperator = ""                ← 运营商筛选（可选）
  templateTargetName = "CCTV-1"        ← 频道名称
  templateTargetAddress = "239.3.1.1:1234"  ← 组播地址
  dataSource = "sub_xxx"               ← 数据源（订阅uid，逗号分隔）
  enabled = true

用户操作: 启动扫描
        │
        ▼
  trigger_background_queue([config_id])            ← engine.py
        │  daemon thread + asyncio.run()
        ▼
  execute_scan_queue(config_ids)                    ← engine.py
        │
        │  ┌──── for each config_id ────┐
        │  │                              │
        ▼  │                              │
  ① 读取 scan_config                       │
        │                                  │
        ▼                                  │
  ② 解析 dataSource → uid 列表              │
     ├─ 非空 → 逗号分隔                     │
     └─ 空 → 所有 enabled=1 的订阅 uid      │
        │                                  │
        ▼                                  │
  ③ 验证 uid 是否 enabled (subs_map)        │
     └─ 未启用/不存在 → 跳过                 │
        │                                  │
        ▼                                  │
  ④ 从 source_cache 过滤指定地区 host        │
     get_cached_hosts(uid, templateRegion)  │
     = SELECT DISTINCT host                 │
       FROM source_cache                    │
       WHERE sourceType=uid                 │
         AND geoRegion='北京'               │
     → ["10.0.1.1:4022", "10.0.2.3:4022"]  │
        │                                  │
        ▼                                  │
  ⑤ 去重：排除已在活源池的 host              │
     get_existing_hosts_batch()             │
     = SELECT DISTINCT host                 │
       FROM hosts                           │
       WHERE host IN (...)                  │
     → 已存在的 host 跳过验证                │
        │                                  │
        ▼                                  │
  ⑥ 并发验证流可用性                         │
     verify_single_host(session, host,      │
       target="239.3.1.1:1234", timeout)    │
     = GET http://HOST/udp/239.3.1.1:1234   │
     尝试 rtp/udp 两种协议                    │
     → 200 + 读到 512B 数据 → 有效           │
     → 其他 → 无效                           │
        │                                  │
        ▼                                  │
  ⑦ geo 富化（跳过 health_check）            │
     enrich_geo_batch(valid_hosts, session, │
       skip_health_check=True)              │
     ├─ 已有 geo → 跳过                     │
     ├─ 查缓存 → 补充                       │
     └─ ip2region 查询 → 补充               │
        │                                  │
        ▼                                  │
  ⑧ 新 geo 回写 source_cache                │
     cache_host_geo_batch(geo_rows)         │
     INSERT OR IGNORE → 已有的不更新         │
        │                                  │
        ▼                                  │
  ⑨ 过滤 geo 为空的 host                     │
     enriched = [item for item              │
       if item.get("geoRegion")]            │
     → geo 为空的不写入 hosts            │
        │                                  │
        ▼                                  │
  ⑩ 写入活源池                              │
     _batch_insert_hosts(batch_rows)        │
     INSERT INTO hosts (                    │
       host, ip, port,                      │
       sourceType, sourceName,              │
       region="北京",      ← 溯源：筛选条件  │
       operator="",        ← 溯源：筛选条件  │
       geoRegion="北京",   ← 属性：真实位置  │
       geoOperator="联通", ← 属性：真实运营商 │
       delay=150,                           │
       protocol="udp",                      │
       target="239.3.1.1:1234",             │
       channelName="CCTV-1"                 │
     )                                      │
     ON CONFLICT(host, target, channelName) │
     DO UPDATE SET delay, updateTime,       │
                   geoRegion, geoOperator   │
        │                                  │
        └─────────────────────────────────┘
```

### 关键点
- **region vs geoRegion**：region 是配置模板值（溯源信息），geoRegion 是 ip2region 实查值（属性信息）
- **verify_single_host 已验证流可用性**，所以 enrich_geo_batch 跳过 health_check
- **ON CONFLICT 更新**：同一 host+target+channelName 重复入库时，只更新 delay/updateTime/geo
- **去重优先**：已在 hosts 的 host 直接跳过，避免重复验证
- **配置间延迟**：扫描完一个配置后等待 config_delay 秒再继续下一个
- **队列机制**：扫描配置是队列任务，同一时间只执行一个配置。正在运行的任务完成后可再次被加入队列

### 队列行为

```
trigger_background_queue([1, 2, 3])
        │  启动队列，逐个执行
        │
  ┌── index=0: 配置1 执行中 ──┐
  │                            │
  │  用户调 POST /configs/1/stop（当前任务）
  │    → interrupt_current=True
  │    → worker 立即退出，engine 跳到 index=1
  │                            │
  ├── index=1: 配置2 执行中 ──┤
  │                            │
  │  用户调 POST /configs/2/stop（当前任务）
  │    → 同上，跳到 index=2
  │                            │
  ├── index=2: 配置3 执行中 ──┤
  │                            │
  │  用户调 POST /configs/1/run（已处理完，重新加入）
  │    → 追加到队列末尾 → [1, 2, 3, 1]
  │    → 配置3 完成后继续执行配置1
  │                            │
  └────────────────────────────┘

停止整个队列: POST /configs/run-all → stop()
  → _should_stop=True + _interrupt_current=True
  → 循环退出，不再自动续跑
```

---

## 四、流程 C：复测淘汰

### 目的
定期验证活源池中所有源是否仍然可用，淘汰两次验证均失败的源。

### 触发

`POST /api/cron/heartbeat` → cron 匹配 `janitor_cron` 设置 → `execute_recheck()`

### 详细流程

```
cron 触发复测
        │
        ▼
  ① 读取 hosts 所有记录
     SELECT id, host, target, protocol FROM hosts
        │
        ▼
  ② 并发验证（与扫描引擎相同的 verify_single_host）
     ├─ 成功 → 更新 delay/updateTime/protocol
     └─ 失败 → 进入二次复测列表
        │
        ▼
  ③ 二次复测（失败的再验证一次）
     ├─ 成功 → 更新 delay/updateTime/protocol（恢复）
     └─ 失败 → 彻底淘汰
        │
        ▼
  ④ 淘汰处理
     ├─ DELETE FROM hosts WHERE id=?
     └─ DELETE FROM source_cache WHERE host=?
         （同步清理缓存，防止下次扫描再次命中）
```

### 关键点
- **两次验证**：首次失败给第二次机会，避免网络抖动误杀
- **source_cache 同步清理**：淘汰的 host 从缓存也删除，防止再次被扫描引擎选中
- **复测与扫描互斥**：扫描启动时暂停复测（_pause_recheck），复测 worker 进入等待

---

## 五、流程 D：认证 & 权限

### 登录流程

```
POST /api/login { password: "xxx" }
        │
        ├─ 密码验证: pbkdf2_hmac(sha256, password, salt, 100000)
        │  兼容旧 SHA-256 哈希（检测前缀 "pbkdf2$" 判断新旧格式）
        │
        ├─ 登录限流: 同一 IP 5 分钟内最多 5 次
        │
        └─ 成功 → 内存 _sessions[token] = {created_at}
           返回 {token, ...}
```

### 中间件认证

```
所有 /api/* 请求 → 检查 X-Auth-Token
  ├─ token 存在且未过期（7天 TTL）→ 放行
  └─ 否则 → 401

豁免路径（无需登录）:
  /api/login, /api/logout,
  /api/source/push (用 X-API-Key),
  /api/cron/heartbeat,
  /api/source-cache/list, /api/source-cache/delete
```

### 推送认证

```
POST /api/source/push
  └─ 检查 X-API-Key == settings.push_api_key
     ├─ 匹配 → 接收数据，后台异步处理
     └─ 不匹配 → 403
```

---

## 六、流程 E：数据源订阅管理

### 订阅生命周期

```
创建订阅 → POST /api/subscriptions
  { name, uid, url, enabled, fetchCron }

手动拉取 → POST /api/subscriptions/{id}/fetch
  → 后台线程执行 fetch_subscription → process_source_data

批量拉取 → POST /api/subscriptions/fetch-all
  → 并发 asyncio.gather 拉取所有启用订阅

定时拉取 → cron 匹配 fetchCron
  → 并发 asyncio.gather 拉取匹配的订阅

更新订阅 → PUT /api/subscriptions/{id}
  → uid 变更时同步更新 source_cache 中的 sourceType

删除订阅 → DELETE /api/subscriptions/{id}
  → 同步删除 source_cache 中对应 sourceType 的所有数据
```

### 订阅拉取流程

```
fetch_subscription(name, uid, url)
        │
        ├─ 在 URL 中追加 sourceType=uid&sourceName=name 参数
        ├─ GET 请求外部 API（30s 超时）
        └─ 解析返回 JSON: { hosts: [{host, geoRegion?, geoOperator?}] }
           │
           ▼
  process_source_data(uid, hosts)
     → enrich_geo_batch → cache_sources
```

---

## 七、定时调度（cron heartbeat）

### 触发方式

外部 crontab 每分钟调用 `POST /api/cron/heartbeat`，服务端匹配当前时间与各 cron 表达式。

### 调度的 3 类任务

| 任务 | cron 设置 | 触发条件 |
|------|-----------|----------|
| 扫描 | `settings.scan_cron` | 匹配时，取所有 enabled=1 的 scan_config，加入扫描队列 |
| 复测 | `settings.janitor_cron` | 匹配且扫描空闲时，启动 `execute_recheck()` |
| 订阅拉取 | `subscriptions.fetchCron` | 每个订阅独立匹配，并发拉取 |

### cron 表达式格式

5 字段：`分 时 日 月 周`，支持 `*`, `*/步长`, `,`枚举, `-`范围

### 防重复执行

`_should_exec(task_key, now)` 按分钟去重，同一分钟内不会重复触发同一任务。

---

## 八、前端 API 一览

| 接口 | 方法 | 认证 | 用途 |
|------|------|------|------|
| `/api/login` | POST | 无 | 登录获取 token |
| `/api/logout` | POST | Token | 登出 |
| `/api/settings` | GET | Token | 获取全局设置 |
| `/api/settings` | PUT | Token | 更新全局设置 |
| `/api/configs` | GET | Token | 列出扫描配置 |
| `/api/configs` | POST | Token | 创建扫描配置 |
| `/api/configs/{id}` | PUT | Token | 更新扫描配置 |
| `/api/configs/{id}` | DELETE | Token | 删除扫描配置 |
| `/api/configs/{id}/run` | POST | Token | 启动单个配置扫描 |
| `/api/configs/{id}/stop` | POST | Token | 停止单个配置 |
| `/api/configs/run-all` | POST | Token | 启动所有启用配置 |
| `/api/configs/progress` | GET | Token | 获取扫描进度 |
| `/api/data-sources` | GET | Token | 获取已启用数据源列表 |
| `/api/subscriptions` | GET | Token | 列出订阅 |
| `/api/subscriptions` | POST | Token | 创建订阅 |
| `/api/subscriptions/{id}` | PUT | Token | 更新订阅 |
| `/api/subscriptions/{id}` | DELETE | Token | 删除订阅 |
| `/api/subscriptions/{id}/fetch` | POST | Token | 手动拉取订阅 |
| `/api/subscriptions/fetch-all` | POST | Token | 批量拉取订阅 |
| `/api/hosts` | GET | Token | 查询活源池（分页+筛选） |
| `/api/hosts/{id}/test-delay` | POST | Token | 测试单个源延迟 |
| `/api/hosts/{id}` | DELETE | Token | 删除单个源 |
| `/api/source-cache/list` | GET | 无 | 列出缓存数据（分页） |
| `/api/source-cache/delete` | POST | 无 | 删除缓存数据 |
| `/api/source/push` | POST | API Key | 外部推送 host |
| `/api/cron/heartbeat` | POST | 无 | 定时心跳触发 |
| `/api/cron/recheck` | POST | Token | 手动触发复测 |
| `/api/change-password` | POST | Token | 修改密码 |
| `/api/logs` | GET | Token | 获取最近日志 |

---

## 九、数据过滤总结

### host 进入 source_cache 的条件（全部满足）

1. health_check 通过（GET /status 返回 "udpxy status"）
2. DNS 可解析为 IP
3. IP 非私有/非内网/非回环（is_private/is_loopback/is_link_local）
4. IP 属于中国内地（ip2region countryCode=CN 且省份在 MAINLAND_REGIONS 中）
5. geoRegion 不为空且在 MAINLAND_REGIONS 中（cache_sources 兜底过滤）

### host 进入 hosts 的条件（全部满足）

1. 在 source_cache 中存在且 geoRegion 匹配 templateRegion
2. 不在 hosts 中（去重）
3. verify_single_host 验证通过（流可用）
4. geoRegion 不为空（DNS 解析失败或 geo 查询失败的过滤掉）

---

## 十、配置与部署

### Docker Compose

```bash
docker compose up --build
# backend → :7860, frontend → :8080
```

- 后端：Python 3.11-slim, uvicorn, 数据卷 `./data:/app/data`
- 前端：Node 20 build → nginx:alpine, 代理 `/api/` → backend:7860

### 环境变量

| 变量 | 默认值 | 用途 |
|------|--------|------|
| `DB_PATH` | `data.db` | 数据库路径（全部表） |
| `UDPXY_SCANNER_PASSWORD` | `admin` | 默认登录密码 |
