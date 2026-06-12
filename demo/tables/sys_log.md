# sys_log

> 操作日志 | 数据库: sushi_test | 字段数: 9 | 索引数: 1 | 预估行数: 1307

## 字段列表

| # | 字段名 | 类型 | 可空 | 默认值 | 键 | 注释 | 值域 | 注释来源 |
|---|--------|------|------|--------|-----|------|------|----------|
| 1 | id | bigint unsigned | NO | AUTO_INCREMENT | PK | 日志ID | - | 数据库 |
| 2 | tenant_id | bigint unsigned | NO | - | - | 租户ID | - | 数据库 |
| 3 | user_id | bigint unsigned | NO | - | - | 用户ID | - | 数据库 |
| 4 | name | varchar(64) | YES | NULL | - | 用户名 | - | 数据库 |
| 5 | title | varchar(255) | YES | NULL | - | 日志标题 | - | 数据库 |
| 6 | type | tinyint | YES | NULL | - | 日志类型 | - | 数据库 |
| 7 | content | text | YES | NULL | - | 日志内容 | - | 数据库 |
| 8 | client_ip | varchar(255) | YES | NULL | - | 访问IP | - | 数据库 |
| 9 | create_time | datetime | NO | on update CURRENT_TIMESTAMP | - | 创建时间 | - | 数据库 |

## 索引

| 索引名 | 类型 | 字段 | 唯一 |
|--------|------|------|------|
| PRIMARY | 主键 | id | YES |

## 外键关系

无外键关系。

## 字段分析记录

> 所有字段注释均来自数据库，无需代码分析或 AI 推测。
