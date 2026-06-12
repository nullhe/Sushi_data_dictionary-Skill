# tenant_department

> 部门信息 | 数据库: sushi_test | 字段数: 11 | 索引数: 1 | 预估行数: 1

## 字段列表

| # | 字段名 | 类型 | 可空 | 默认值 | 键 | 注释 | 值域 | 注释来源 |
|---|--------|------|------|--------|-----|------|------|----------|
| 1 | id | bigint unsigned | NO | AUTO_INCREMENT | PK | 部门ID | - | 数据库 |
| 2 | tenant_id | bigint unsigned | NO | - | - | 归属租户ID | - | 数据库 |
| 3 | name | varchar(64) | NO | - | - | 部门名称 | - | 数据库 |
| 4 | code | varchar(64) | NO | - | - | 部门编码 | - | 数据库 |
| 5 | manager_id | bigint unsigned | YES | NULL | - | 负责人ID | - | 数据库 |
| 6 | area | varchar(255) | YES | NULL | - | 部门区域 | - | 数据库 |
| 7 | address | varchar(255) | YES | NULL | - | 办公地址 | - | 数据库 |
| 8 | pid | bigint | NO | - | - | 上级部门ID | - | 数据库 |
| 9 | status | tinyint | YES | NULL | - | 状态 | - | 数据库 |
| 10 | seq | int | NO | - | - | 顺序 | - | 数据库 |
| 11 | create_time | datetime | YES | NULL | - | 创建时间 | - | 数据库 |

## 索引

| 索引名 | 类型 | 字段 | 唯一 |
|--------|------|------|------|
| PRIMARY | 主键 | id | YES |

## 外键关系

无外键关系。

## 字段分析记录

> 所有字段注释均来自数据库，无需代码分析或 AI 推测。
