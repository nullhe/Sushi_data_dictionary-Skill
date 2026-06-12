---
name: db-dict
description: "连接 MySQL 数据库，读取所有表结构，结合项目代码智能补全字段注释，解析 Java 实体类，生成 Markdown + HTML 数据字典文档。"
version: 1.0.0
allowed_tools: ["Bash", "Read", "Write", "Grep", "Glob", "Agent", "AskUserQuestion"]
---

# db-dict - MySQL 数据字典生成器

连接 MySQL 数据库，读取全部表结构元数据，结合本地 Java 项目代码（实体类、枚举、JSP、Mapper XML）智能分析并补全缺失字段注释，输出结构化的 Markdown 数据字典文件和带搜索筛选功能的 HTML 总览页。

## 触发条件

使用此 Skill 当：
- 用户调用 `/db-dict`
- 用户要求生成数据库字典/数据字典
- 用户要求导出数据库表结构文档

## 输出目录

```
docs/data-dictionary/
├── index.html              # HTML 总览页（带搜索/筛选/统计）
├── summary.md              # 统计摘要
├── server.py               # 本地服务器（支持在线编辑注释）
└── tables/
    ├── table_name.md       # 每表一个 Markdown 文件
    └── ...
```

---

## 完整工作流

### Phase 1: 获取数据库连接信息

交互式询问用户以下信息（如果未通过参数提供）：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| host | 数据库主机 | localhost |
| port | 端口 | 3306 |
| user | 用户名 | root |
| password | 密码 | (交互输入，不回显) |
| database | 数据库名 | (必填) |
| tables | 表名过滤（支持通配符 `*`） | 所有表 |
| server-port | 本地编辑服务器端口 | 8080 |

**安全要求**：
- 密码通过交互输入，不在命令行历史中留下痕迹
- 连接信息不写入任何输出文件
- 可通过环境变量 `DB_DICT_HOST`, `DB_DICT_PORT`, `DB_DICT_USER`, `DB_DICT_PASS`, `DB_DICT_DB` 预设

**编码要求**：

所有 `mysql` 命令必须带 `--default-character-set=utf8mb4`，否则中文注释会乱码。Windows 环境下尤其注意，cmd 默认编码为 GBK。

```bash
mysql -h "$HOST" -P "$PORT" -u "$USER" -p"$PASS" --default-character-set=utf8mb4 "$DB" -e "SELECT 1"
```

**Windows 编码补充**：

如果终端输出仍然乱码，在 Python 脚本中读取文件时使用 `errors='replace'`：
```python
with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
    ...
```

### Phase 2: 提取数据库元数据

#### 2.0 分片表识别（重要）

很多数据库使用分片表（如 `order_slice1` ~ `order_slice20`），结构与主表完全相同。**必须识别并跳过分片表**，否则会生成大量重复文件。

**识别规则**：
- 表名包含 `_slice` 后跟数字（如 `alibabaorder_slice3`）
- 同一主表的分片表结构完全相同，只需保留主表定义

**处理策略**：
1. 先获取所有表名列表
2. 按主表名分组（去掉 `_slice\d+` 后缀）
3. 每组只保留主表（无 `_slice` 后缀的），跳过分片表
4. 在统计摘要中分别记录"数据库总表数"和"文档生成表数"

**SQL 过滤**（可选）：
```sql
-- 排除分片表
WHERE TABLE_SCHEMA = '{database}'
  AND TABLE_NAME NOT REGEXP '_slice[0-9]+$'
```

#### 2.1 获取表列表

```sql
SELECT
    TABLE_NAME,
    TABLE_COMMENT,
    TABLE_ROWS,
    DATA_LENGTH,
    INDEX_LENGTH,
    CREATE_TIME,
    UPDATE_TIME,
    TABLE_COLLATION
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = '{database}'
  AND TABLE_TYPE = 'BASE TABLE'
ORDER BY TABLE_NAME;
```

#### 2.2 获取字段详情

```sql
SELECT
    c.TABLE_NAME,
    c.ORDINAL_POSITION,
    c.COLUMN_NAME,
    c.COLUMN_TYPE,
    c.DATA_TYPE,
    c.CHARACTER_MAXIMUM_LENGTH,
    c.NUMERIC_PRECISION,
    c.NUMERIC_SCALE,
    c.IS_NULLABLE,
    c.COLUMN_DEFAULT,
    c.COLUMN_COMMENT,
    c.COLUMN_KEY,
    c.EXTRA,
    kcu.REFERENCED_TABLE_NAME,
    kcu.REFERENCED_COLUMN_NAME
FROM information_schema.COLUMNS c
LEFT JOIN information_schema.KEY_COLUMN_USAGE kcu
    ON c.TABLE_SCHEMA = kcu.TABLE_SCHEMA
    AND c.TABLE_NAME = kcu.TABLE_NAME
    AND c.COLUMN_NAME = kcu.COLUMN_NAME
    AND kcu.REFERENCED_TABLE_NAME IS NOT NULL
WHERE c.TABLE_SCHEMA = '{database}'
ORDER BY c.TABLE_NAME, c.ORDINAL_POSITION;
```

#### 2.3 获取索引信息

```sql
SELECT
    TABLE_NAME,
    INDEX_NAME,
    NON_UNIQUE,
    SEQ_IN_INDEX,
    COLUMN_NAME,
    INDEX_TYPE,
    CASE
        WHEN INDEX_NAME = 'PRIMARY' THEN '主键'
        WHEN NON_UNIQUE = 0 THEN '唯一'
        ELSE '普通'
    END AS INDEX_TYPE_CN
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = '{database}'
ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX;
```

#### 2.4 获取外键关系

```sql
SELECT
    TABLE_NAME,
    COLUMN_NAME,
    CONSTRAINT_NAME,
    REFERENCED_TABLE_NAME,
    REFERENCED_COLUMN_NAME
FROM information_schema.KEY_COLUMN_USAGE
WHERE TABLE_SCHEMA = '{database}'
  AND REFERENCED_TABLE_NAME IS NOT NULL
ORDER BY TABLE_NAME;
```

**执行方式**：将上述 SQL 通过 `mysql -e` 执行，输出制表符分隔格式便于解析。

```bash
mysql -h "$HOST" -P "$PORT" -u "$USER" -p"$PASS" --default-character-set=utf8mb4 "$DB" -N -e "..." 2>/dev/null
```

### Phase 3: 代码智能分析

对数据库中 `COLUMN_COMMENT` 为空的字段，按以下优先级从项目代码中提取含义。

#### 3.1 实体类匹配

**查找规则**：

| 表名 | 实体类匹配策略 |
|------|---------------|
| `order_info` | 1) `@TableName("order_info")` 精确匹配<br>2) `OrderInfo.java` 驼峰转换匹配 |
| `stock` | 1) `@TableName("stock")` 精确匹配<br>2) `StockInfo.java` 加 Info 后缀匹配 |
| `goods_record` | 1) `@TableName("goods_record")` 精确匹配<br>2) `GoodsRecordInfo.java` 去下划线驼峰+Info |

**实体类搜索路径**：
- `your-project/src/main/java/com/yourpackage/domain/` (主实体)
- `your-project/src/main/java/com/yourpackage/domain/vo/` (VO/DTO)

**字段注释提取规则**（按优先级）：

1. **Javadoc 注释**：`/** 中文描述 column_name **/` → 提取中文描述部分
2. **行内注释**：`// 中文描述` → 提取注释文本
3. **@TableField 注解**：`@TableField(value = "column_name")` → 确认字段映射关系
4. **@JSONField 注解**：`@JSONField(serialize = false)` → 标记为内部字段

**字段映射方法**：
- 数据库 `snake_case` 列名 → Java 全小写字段名（去下划线）：`receiver_name` → `receivername`
- 或通过 MyBatis XML `<resultMap>` 中的 `column` → `property` 映射

#### 3.2 枚举类分析

**搜索路径**：`your-project/src/main/java/com/yourpackage/domain/enums/`

**匹配方式**：
- 如果实体类字段类型引用了枚举类（如 `OrderStatusEnums`）
- 如果字段注释中包含枚举值说明（如 `0.等待审核 1.审核中`）
- 解析枚举类中的常量定义，提取 `code → 含义` 映射

**提取格式**：`0=待付款, 1=已付款, 2=已发货, 3=已完成, 4=已取消`

#### 3.3 JSP 前端分析

**搜索路径**：`your-project/src/main/webapp/WEB-INF/views/`

**匹配方式**：
- 在 JSP 文件中搜索 `name="{java_field_name}"` 的 input/select/textarea 元素
- 提取同一行或前一行的 label 文本
- 提取 EasyUI `data-options` 中的 `prompt` 或 `missingMessage` 属性

**示例**：
```jsp
<!-- 从 JSP 中提取到 "买家昵称" -->
<td>买家昵称:</td>
<td><input name="buynick" class="easyui-textbox" /></td>
```

#### 3.4 Mapper XML 分析（实现指南）

**搜索路径**：`your-project/src/main/resources/mybatis/`

**具体实现步骤**：

1. **提取 resultMap 映射**：解析 `<resultMap>` 中的 `column` → `property` 对应关系
   ```xml
   <resultMap id="BaseResultMap" type="StockInfo">
       <result column="stocknum" property="stocknum" jdbcType="INTEGER"/>
   </resultMap>
   ```

2. **从 SQL 注释提取**：MyBatis XML 中的 SQL 有时包含字段注释
   ```xml
   <!-- 库存数量 -->
   <result column="stocknum" property="stocknum"/>
   ```

3. **从使用上下文推断**：
   - WHERE 条件中的字段通常是筛选/查询字段
   - ORDER BY 中的字段通常是排序/时间字段
   - GROUP BY 中的字段通常是分类/维度字段
   - SUM/AVG/COUNT 中的字段通常是数值/统计字段

4. **从关联查询推断**：JOIN 条件中的字段通常是外键或关联标识

#### 3.5 VO 类分析

**搜索路径**：`your-project/src/main/java/com/yourpackage/domain/vo/`

**匹配方式**：
- VO 类中扩展的字段（通过 JOIN 查询获得）
- VO 类中对原字段的重命名或计算字段

#### 3.6 上下文感知的 AI 推测（兜底）

当以上所有来源都无法提供注释时，使用**上下文感知**的推测策略：

**第一层：同表字段语义关联**
- 如果表中有 `orderid`，则该表的其他字段大概率与订单相关
- 如果表中有 `goodsid`，则该表的其他字段大概率与商品相关
- 如果表中有 `shopid`，则该表的其他字段大概率与店铺相关

**第二层：字段名模式匹配**
- `xxxid` / `xxx_id` → 如果 xxx 对应已知表名，则为"xxx表ID"（如 `brand_id` → "品牌ID"）
- `xxxname` / `xxx_name` → "xxx名称"
- `xxxtype` / `xxx_type` → "xxx类型"
- `xxxstatus` / `xxx_status` → "xxx状态"
- `xxxtime` / `xxx_time` → "xxx时间"
- `xxxprice` / `xxx_price` → "xxx价格"
- `xxxnum` / `xxx_num` → "xxx数量"
- `isxxx` / `is_xxx` → "是否xxx"

**第三层：字段类型推断**
- `tinyint(1)` + 只有 0/1 值 → 布尔标志位
- `decimal(M,N)` → 金额或价格
- `datetime` → 时间戳
- `text` / `longtext` → 大文本内容（备注、描述、JSON 数据）

**第四层：外键关系推断**
- 引用 `warehouse.id` → 仓库标识
- 引用 `brand.id` → 品牌标识
- 引用 `tenant.id` → 租户标识

**输出格式**：`[待补充] 基于字段名推测的含义` 或 `[待补充] xxx相关属性`（xxx 为表的业务含义）

### Phase 4: 生成 Markdown 文件

#### 4.1 单表 Markdown 模板

每张表生成 `docs/data-dictionary/tables/{table_name}.md`：

```markdown
# {table_name}

> {table_comment} | 数据库: {database} | 字段数: {column_count} | 索引数: {index_count} | 预估行数: {row_count}

## 字段列表

| # | 字段名 | 类型 | 可空 | 默认值 | 键 | 注释 | 值域 | 注释来源 |
|---|--------|------|------|--------|-----|------|------|----------|
| 1 | id | bigint(20) | NO | AUTO_INCREMENT | PK | 主键ID | - | 数据库 |
| 2 | status | tinyint(4) | NO | 0 | - | 订单状态 | 0=待付款,1=已付款,2=已发货 | 实体类注释 |
| ... |

## 索引

| 索引名 | 类型 | 字段 | 唯一 |
|--------|------|------|------|
| PRIMARY | 主键 | id | YES |
| idx_status | 普通 | status | NO |
| ... |

## 外键关系

| 本表字段 | 关联表 | 关联字段 | 关系 |
|----------|--------|----------|------|
| shopid | shop_info | id | N:1 |
| ... |

## 字段分析记录

> 以下字段注释由代码分析或 AI 推测补充，标注了来源和置信度。

| 字段名 | 补充注释 | 来源 | 置信度 |
|--------|----------|------|--------|
| omstype | 订单商品来源类型 | AI推测 | 低 |
| buyernick | 买家昵称 | JSP标签 | 高 |
| ... |
```

#### 4.2 summary.md 模板

```markdown
# 数据字典 - 统计摘要

> 数据库: {database} | 生成时间: {datetime} | 工具: db-dict skill

## 概览

| 指标 | 值 |
|------|-----|
| 数据库总表数 | {db_total_tables} |
| 分片表数 | {slice_tables} |
| 文档生成表数 | {doc_tables} |
| 总字段数 | {total_columns} |
| 有数据库注释的字段 | {db_commented} ({pct}%) |
| 代码分析补充的字段 | {code_analyzed} ({pct}%) |
| AI 推测的字段 | {ai_inferred} ({pct}%) |
| 待补充的字段 | {pending} ({pct}%) |

## 表清单

| 表名 | 注释 | 字段数 | 注释覆盖率 |
|------|------|--------|-----------|
| order_info | 订单主表 | 52 | 78% |
| stock_info | 库存表 | 35 | 45% |
| ... |
```

### Phase 5: 生成 HTML 总览页

HTML 生成使用**外部模板文件** + **占位符替换**，避免 Python f-string 与 JavaScript 花括号冲突。

**模板文件**：`scripts/template.html`
**生成脚本**：`scripts/generate_html.py`

**调用方式**：

```bash
python scripts/generate_html.py \
  --input-dir "docs/data-dictionary/tables" \
  --output "docs/data-dictionary/index.html" \
  --database "{database}" \
  --db-total-tables {db_total_tables} \
  --slice-tables {slice_tables} \
  --entities-dir "your-project/src/main/java/com/yourpackage/domain" \
  --api-base ""
```

**实体类解析**：`--entities-dir` 参数指定 Java 实体类目录，脚本自动解析：
- `@TableName("table_name")` 映射
- `private Type fieldName;` 字段声明
- `/** 中文注释 */` 和 `// 行内注释`
- `@TableField(value = "column_name")` 列映射
- 跳过 `serialVersionUID` 和 `@TableField(exist = false)` 字段

**HTML 功能要求**：
- 左侧菜单栏：
  - 搜索框 + 搜索按钮在侧边栏最上方（点击按钮或按 Enter 触发搜索，不实时搜索）
  - 两个主菜单：「数据库表」和「项目实体」
  - 每个主菜单下按首字母 A-Z 排序的扁平列表（无二级分组）
  - 列表超过一屏时显示滚动条（max-height: 45vh）
  - 点击菜单项只展示该项内容
  - 点击主菜单标题折叠/展开
  - 「显示全部」按钮恢复全部展示
  - 搜索支持表名、字段名、注释内容匹配；清空搜索框点击搜索恢复全部
- 右侧：字段详情表格
- 顶部：统计面板（总表数、总字段数、注释覆盖率）
- 标签高亮：数据库注释=绿色、代码推断=蓝色、AI推测=橙色、待补充=红色
- 响应式布局，支持移动端查看
- 纯静态，无外部依赖（CSS/JS 内联）
- 点击字段注释或表注释可在线编辑，保存后同步到 .md 文件

**关键实现约束**：
- HTML 模板中的 JavaScript 使用原生 `{}` 语法，**禁止使用 Python f-string 生成 HTML**
- 使用 `str.replace('__PLACEHOLDER__', value)` 或 `string.Template` 进行变量替换
- JSON 数据通过 `<script>const DATA = __JSON_DATA__;</script>` 注入

### Phase 6: 生成本地编辑服务器

将 `server.py` 从 skill 脚本目录复制到输出目录，并注入用户指定的端口号。

**模板文件**：`scripts/server.py`

**生成方式**：

1. 读取模板文件内容
2. 将默认端口 `8080` 替换为用户指定的端口
3. 写入 `docs/data-dictionary/server.py`

```bash
# 复制 server.py 到输出目录
cp scripts/server.py docs/data-dictionary/server.py
```

如果用户指定了非 8080 的端口，修改 `server.py` 中的默认端口值：
```python
parser.add_argument("--port", type=int, default={user_port}, help="端口号 (默认 {user_port})")
```

**server.py 功能**：
- `GET /` — 返回 index.html
- `GET /tables/<name>.md` — 返回 md 文件
- `POST /api/save-comment` — 保存字段/表注释到 .md 文件
- CORS 支持，纯标准库无外部依赖
- 双栈监听 IPv4 + IPv6（Firefox 兼容）

**生成后询问用户**是否立即启动服务器。如果用户同意：

```bash
cd docs/data-dictionary && python server.py
```

并提示用户在浏览器中打开 `http://localhost:{port}`。

### Phase 7: 输出统计

完成所有表的处理后，输出执行摘要：

```
╔══════════════════════════════════════════════════╗
║         数据字典生成完成                          ║
╠══════════════════════════════════════════════════╣
║  数据库: {database}                              ║
║  数据库总表数: {db_total_tables}                 ║
║  分片表数:    {slice_tables} (已跳过)            ║
║  文档生成表数:   {doc_tables}                    ║
║  总字段: {total_columns}                         ║
║                                                  ║
║  注释来源分布:                                    ║
║  ├── 数据库原有注释:  {db_commented} ({pct1}%)   ║
║  ├── 代码分析补充:    {code_analyzed} ({pct2}%)  ║
║  ├── AI 推测:         {ai_inferred} ({pct3}%)    ║
║  └── 待补充:          {pending} ({pct4}%)        ║
║                                                  ║
║  输出位置: docs/data-dictionary/                 ║
║  ├── Markdown: docs/data-dictionary/tables/      ║
║  ├── HTML: docs/data-dictionary/index.html       ║
║  └── Server: docs/data-dictionary/server.py      ║
╚══════════════════════════════════════════════════╝
```

---

## 执行注意事项

### 性能

- 大表（>100 字段）的代码分析可能耗时较长，使用 Agent 并行分析多张表
- 每批次处理 5-10 张表，避免上下文溢出
- 使用 `Grep` 工具搜索代码，不要用 `Bash` + `grep`
- **必须跳过分片表**（`_slice\d+`），否则会生成数千个重复文件

### 准确性

- 实体类字段匹配时，优先使用 `@TableName` 注解，其次使用文件名匹配
- AI 推测的注释必须标记 `[待补充]` 前缀，不可当作确定信息
- 枚举值域提取时，注意处理注释中的多种格式（顿号分隔、换行分隔等）
- Mapper XML 分析时，优先从 resultMap 注释和 SQL 注释中提取，其次从使用上下文推断

### 安全

- 数据库密码不写入任何文件
- 生成的 HTML 中不包含连接信息
- 临时文件（原始数据、生成脚本）在完成后删除

### 增量更新

- 如果 `docs/data-dictionary/tables/` 目录已存在，询问用户是全量重新生成还是增量更新
- 增量模式：只处理新增/变更的表，保留已有的人工补充注释
- 通过比对 `_summary.json` 中的时间戳判断是否需要更新

### 统计准确性

统计摘要必须区分以下指标：
- **数据库总表数**：`information_schema.TABLES` 中的全部表数量
- **分片表数**：符合 `_slice\d+` 模式的表数量
- **文档生成表数**：实际生成 Markdown 文件的表数量（排除分片表）
- **总字段数**：文档生成表中的字段总数（不是数据库全部字段）
