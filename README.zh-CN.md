# Agent Workflow Audit

面向智能体工程流程的离线记录与审计工具。当前版本为 0.1.0，已在本地 Windows / Python 3.12 验证。

本包可以验证证据文件、关联执行记录、统计历史版本投入，并检查验收记录是否绑定具体版本。
流程阶段由输入数据配置。它不负责调用模型、调度引擎或执行游戏测试。

## 开始使用

```console
python -m pip install .
awa audit examples/minimal/dataset.json --evidence-root examples/minimal/evidence --out reports/demo
```

打开 `reports/demo/report.html`。示例数据全部为合成数据，故意包含缺失证据、哈希不一致、无执行关联和验收版本不明确的情形。
这些数据只用于验证工具，不能计入论文或 Slowlife 实验结果。

## Slowlife 下一步

1. 按 [接入说明](docs/slowlife.md) 确定任务纳入规则、实际阶段、停止条件和主要指标。
2. 填写 `profiles/slowlife.protocol.draft.json` 并冻结为本地协议；当前模板未冻结，也没有预注册。
3. 在任务开始前记录任务、初始版本、条件和预算，随后记录每次执行、修订、证据和验收决策。
4. 导出独立快照，保存外部清单哈希，再进行分析。失败、取消和未完成任务同样保留。

默认采用前瞻观察研究。只有明确对照条件、分配方式、预算规则和独立结果评估以后，才能按受控比较设计解释。
同一开发者、同一机器上的第二项目能检验流程迁移性，但不能代表独立团队验证。

## 与原论文的关系

作者：Wang Jiayi，Independent Researcher，China。[论文阅读稿](https://github.com/GaryFigno/agent-workflow-audit/releases/download/v0.1.0/paper1-jss-manuscript.pdf)采用 JSS 模板，尚未经过期刊同行评审或录用。论文保留独立版权，代码的 MIT 许可不覆盖论文和真实研究数据。

`studies/paper1/` 保存第一篇的冻结分析源码和输入哈希。真实记录单独存放，提供给
`python tools/verify_paper1.py --source <原复算目录> --out reports/paper1` 即可复算并检查通用工具。
该命令不会运行游戏，也不会修改原始复算包。Slowlife 的新数据使用不同的 dataset_id 和协议，禁止混入旧案例。

## 发布内容

代码、文档、合成示例采用 MIT 许可证。真实生产数据、商业资产、原始会话和本地配置没有装入公开仓库包。
软件作者署名为 Wang Jiayi，并保留项目贡献者版权。仓库未声明 DOI 或期刊录用。

完整命令、数据格式和限制见 [README](README.md)、[数据说明](docs/schema.md) 和 [发布说明](docs/releasing.md)。
