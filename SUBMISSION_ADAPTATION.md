# 官方提交格式适配说明

本次适配不修改分子对接算法、模型、后端业务逻辑或前端功能，只调整比赛提交包装与运行依赖。

## 已完成

- 新增唯一官方 Skill：`skills/docking-copilot/SKILL.md`。
- 添加合法 YAML frontmatter：`name=docking-copilot`，description 使用第三人称并包含触发场景。
- 主 Skill 压缩到 500 行以内。
- 详细 Schema、工作流、参数、结果解释、失败案例、复现、安全和证据材料放入同层 `references/`。
- 移除根目录旧 `SKILL.md`，避免出现两个 Skill 入口。
- 根目录 `requirements.txt` 改为 Linux 官方沙箱额外依赖；Mac 本地 `environment.yml` 保留。
- 新增 `check_runtime.py`、`run_example.py` wrapper、`validate_submission.py`。
- 更新提交检查器中的 50MB/10MB 规则和官方 Skill 路径。
- 更新提交说明中的旧 250MB / 12h 规则。
- README 仅追加官方 Skill 入口说明。

## 未修改

- `backend/app/` 对接算法与工作流实现。
- `models/`。
- `frontend/src/`。
- `schemas/` 的业务字段。
- Notebook 的科研计算内容。
- 既有结果文件与测试证据。
