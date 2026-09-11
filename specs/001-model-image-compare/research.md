# Research: 设计决策与证据

## 调用层

- Decision：HTTPX共用请求函数、提供方参数映射及校验；用户已确认。
- Rationale：需记录最终请求和首次原文，模型能力差异不能由统一接口消除。
- Alternatives considered：LangChain统一调用仍需处理温度固定、预算缺失，暂不引入。
- Evidence：[模型兼容性报告](model-compatibility.md)及其中官方链接，已在前一轮研究；本轮复用结果，不宣称再次实时查询。

## 本地运行

- Decision：FastAPI同源静态页面，SQLite + 本地文件，HTTPX异步请求，Pillow处理图片。
- Rationale：单人本地使用、无生产服务依赖，现有Python骨架可直接扩展。
- Alternatives considered：独立前端构建、外部数据库、队列增加部署工作；纯脚本无法满足页面和历史交互。
- Evidence：前轮已查阅 [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/)、[HTTPX async](https://www.python-httpx.org/async/)、[sqlite3](https://docs.python.org/3/library/sqlite3.html)、[Pillow Image](https://pillow.readthedocs.io/en/stable/reference/Image.html)。具体限值是设计决定。

## 输入与复现

- Decision：完整JSON提示词可编辑，events输入明确code/name/match/exclude/uncertain，允许集合从该文本提取，发送原文；预处理一次复用同一文件。
- Rationale：避免隐藏事件目录与用户文本不一致，统一请求视觉内容；不承诺服务商内部tokenization相同。
- Alternatives considered：自由散文自动提取事件有猜测风险；隐藏拼接提示词不符合可解释对比。
- Evidence：hos-analysis的QwenScreeningClient.screen和_qwen_event_payload。默认事件材料只能标记历史种子，不能冒充当前生产配置。

## 严格参数模式

- Decision：第一版要求显式temperature与MAX_TOKENS；开启思考时要求有效数值budget，关闭时budget=null且省略。暂不启用“不指定而使用各家默认”的宽松模式。
- Rationale：规格要求同等参数；缺省并不等价。缺少数值预算的提供方会在开启思考时阻止运行，用户可切换非思考或取消该模型。
- Alternatives considered：把effort等同token预算、静默省略temperature均不满足公平对比。
- Evidence：兼容性矩阵。MAX_TOKENS定义总生成上限；百炼映射max_completion_tokens；Kimi思考模式总量语义未确证则禁用该配置。

## 未知事实的明确处理

实际提供方尚未由用户指定；部分专属上限尚缺证据。决策是能力表为每个profile记录来源与可验证范围，未确认项禁用，不能填推测数值。本地功能开发和fake测试可进行，真实四模型验收不得标为完成。开发接入步骤必须补足实际地域/端点证据再启用。

四模型非思考temperature=0.6仅为官方渠道兼容候选；不代表其他参数、账号或端点已经通过。价格默认未知，可靠计价快照和对应usage分类齐全才计算。
