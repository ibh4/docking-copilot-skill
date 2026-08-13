# 官方评审沙箱适配

- 运行环境：Docker / Linux。
- 资源：2 CPU / 4 GB RAM / 无 GPU。
- 单任务超时：900 秒。
- 提交包：≤50 MB；单文件：≤10 MB。
- 常见科学栈由官方预装；根目录 `requirements.txt` 仅声明额外依赖。
- 本仓库 `environment.yml` 继续服务于 Mac mini M4 本地开发，不作为官方沙箱安装入口。
- 正式评测建议在请求中显式设置 `docking_parameters.cpu=2`，并保持默认或较低 `exhaustiveness`，避免 2 核环境过度并发。
- 网页前端不是官方任务执行的必要依赖；核心 Skill 可通过 Python 工作流直接运行。
