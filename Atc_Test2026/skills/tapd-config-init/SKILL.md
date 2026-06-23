# TAPD Config Init Skill

用于初始化与升级 TAPD 项目本地配置文件（`.tapd/project_config.json`）。

## 何时使用

- 首次接入 TAPD Skill，需要快速生成本地配置文件。
- 模板新增字段后，需要把缺失字段自动补齐到本地配置。
- 需要保证升级过程不覆盖用户已有配置值。

## 默认路径

- 模板：`prcoess_skill/.tapd/project_config.template.json`
- 本地：`prcoess_skill/.tapd/project_config.json`

## 执行方式（直接执行）

```powershell
python ".cursor/skills/tapd/tapd-config-init/scripts/init_tapd_config.py"
```

可选参数：

```powershell
python ".cursor/skills/tapd/tapd-config-init/scripts/init_tapd_config.py" `
  --template "prcoess_skill/.tapd/project_config.template.json" `
  --target "prcoess_skill/.tapd/project_config.json"
```

## 行为规则

1. 若目标配置不存在：直接按模板创建。
2. 若目标配置已存在：递归补齐缺失 key。
3. 已有 key 永不覆盖（包括基础字段和嵌套字段）。
4. 输出 JSON 结果，包含：
   - `status`：`created` / `merged` / `skipped`
   - `template_path`
   - `target_path`
   - `added_keys`（本次新增字段路径列表）

## 结果判定

- `created`：首次创建成功。
- `merged`：已有文件，本次补齐了缺失字段。
- `skipped`：已有文件且无缺失字段（幂等）。
