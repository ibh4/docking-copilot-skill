# 模型资产说明 / Model Assets

## binding_xgboost_v3.pkl（蒸馏 XGBoost 结合筛选模型）

| 项目 | 说明 |
|---|---|
| 模型类型 | `xgboost.sklearn.XGBClassifier`（objective: `binary:logistic`） |
| 训练数据 | BindingDB 公开结合活性数据（选手自主蒸馏训练，非官方提供） |
| 体积 | 约 2.4 MB |
| 用途 | 对接候选分子的**辅助初筛/排序**：在 Vina 对接前后作为快速结合可能性筛查器，缩小需要精细对接或人工复核的候选集 |
| 加载方式 | `import pickle; model = pickle.load(open("binding_xgboost_v3.pkl","rb"))`，依赖 `xgboost` 库 |

### 使用边界（与本项目科学限制一致）

- 该模型输出为**相对筛查概率**，不是结合自由能，也不能换算为 Kd/Ki/IC50；
- 仅作批内或同分布数据的相对排序参考，不与 Vina 打分直接加权混用；
- 本项目主对接流程（SKILL.md）仍以 AutoDock Vina 为准，本模型为可选增强组件，未接入自动评分链以避免引入不可控偏差。

### 数据来源声明

模型由选手基于公开 BindingDB 数据自主训练与蒸馏，不依赖任何官方知识库或标准答案；训练细节与特征定义见选手历史工作记录（`v22_stable_full/Reference/`）。
