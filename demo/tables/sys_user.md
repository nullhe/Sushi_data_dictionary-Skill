# sys_user

> 管理员信息 | 数据库: sushi_test | 字段数: 19 | 索引数: 1 | 预估行数: 35

## 字段列表

| # | 字段名 | 类型 | 可空 | 默认值 | 键 | 注释 | 值域 | 注释来源 |
|---|--------|------|------|--------|-----|------|------|----------|
| 1 | id | bigint unsigned | NO | AUTO_INCREMENT | PK | 管理员ID | - | 数据库 |
| 2 | tenant_id | bigint | YES | NULL | - | 租户ID | - | 数据库 |
| 3 | department_id | bigint | YES | NULL | - | 部门ID | - | 数据库 |
| 4 | role_id | bigint | YES | NULL | - | 角色ID | - | 数据库 |
| 5 | name | varchar(64) | NO | - | - | 账号名称 | - | 数据库 |
| 6 | nick | varchar(64) | YES | NULL | - | 昵称 | - | 数据库 |
| 7 | password | varchar(64) | NO | - | - | 密码 | - | 数据库 |
| 8 | mobile | varchar(32) | YES | NULL | - | 手机号码 | - | 数据库 |
| 9 | email | varchar(64) | YES | NULL | - | 邮箱地址 | - | 数据库 |
| 10 | atype | tinyint unsigned | NO | 0 | - | 账号权限 | - | 数据库 |
| 11 | tatype | tinyint unsigned | YES | 0 | - | 账号权限 | - | 数据库 |
| 12 | status | tinyint unsigned | NO | 0 | - | 状态 | - | 数据库 |
| 13 | create_time | datetime | NO | - | - | 创建时间 | - | 数据库 |
| 14 | login_time | datetime | YES | NULL | - | 上次登录时间 | - | 数据库 |
| 15 | old_pwd | varchar(255) | YES | NULL | - | 之前的密码 | - | 数据库 |
| 16 | ip_address | varchar(255) | YES | NULL | - | 最近一次登录IP | - | 数据库 |
| 17 | is_expired | tinyint(1) | YES | 0 | - | 账号没有过期 | - | 数据库 |
| 18 | is_locked | tinyint(1) | YES | 0 | - | 账号没有锁定 | - | 数据库 |
| 19 | is_cert_expired | tinyint(1) | YES | 0 | - | 证书没有过期 | - | 数据库 |

## 索引

| 索引名 | 类型 | 字段 | 唯一 |
|--------|------|------|------|
| PRIMARY | 主键 | id | YES |

## 外键关系

无外键关系。

## 字段分析记录

> 所有字段注释均来自数据库，无需代码分析或 AI 推测。
