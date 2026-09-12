# hos-vlm-lab

## 项目目标与需求来源

本项目是多模态视觉模型评测与 Prompt 调优 Demo，用真实业务场景的识别效果和调用成本支持模型筛选。
需求来源：ChatGPT 对话「多模态模型评测 Demo」，会话 ID `6aa2cd02-36fc-83ee-9850-7c1189f18ebf`。

用户明确要求：
- 对比多个多模态模型在所需检测场景上的识别率，兼顾准确度和经济性。
- 支持调整提示词，并查看识别／检测结果。
- 当前五个模型配置槽位为 `DeepSeek-V4.1-Flash`、`qwen3.6-flash`、`qwen3.8-flash`、`kimi-2.6`、`qwen3.6-27b`；27B 使用独立 base_url 和 api_key。

上述名称来自用户描述；接入前核实实际服务商、API model ID、视觉输入能力、参数及计费规则。历史对话中的价格、性能表和示例结果不是已验证数据。

## 业务场景

| 类别 | 场景／目标 |
| --- | --- |
| 基础目标 | 人员、汽车、动物、手提包、背包、行李箱 |
| 人员状态与行为 | 人员站立、摔倒／倒地、人员状态异常、玩手机 |
| 佩戴检查 | 佩戴／未佩戴安全帽、佩戴／未佩戴工牌 |
| 消防 | 明火燃烧、异常烟雾、吸烟、人为纵火 |
| 治安 | 肢体冲突／争执、人员持凶、违规闯入、人群异常聚集、聚众拉横幅 |
| 高危行为 | 违规攀爬、落水或溺水风险 |
| 环境卫生 | 垃圾未清理、垃圾溢出 |
| 交通与秩序 | 车辆阻塞交通、交通事故、违规占道、违规遛宠物 |
| 基础设施 | 路面破损、渗水、土石滑落 |

实现前明确场景拆分、正负例和判定条件，不直接采用历史回复的“34 项”计数。违规类场景可能需要区域／业务规则；时序事件可能需要连续帧，不能把单图猜测视为已证实事件。

## 当前实现与入口

- Python 3.12+ / uv，FastAPI + LangChain ChatOpenAI + HTTPX，原生 HTML/JS/CSS，SQLite + 图片文件；依赖与版本以 pyproject.toml / uv.lock 为准。
- `uv run hos-vlm-lab` 启动单进程本机服务 `127.0.0.1:8000`。启动入口自动加载当前工作目录的 `.env`，已有环境变量优先，文件不存在时跳过。
- `uv run pytest -q` 使用 fake / MockTransport 和临时数据；`uv build` 构建包。
- `uv run python -m tests.browser_app --data-dir .test-data/browser` 启动仅测试用模拟页面 `127.0.0.1:8001`，拒绝出站网络，不代表真实检测。
- `src/hos_vlm_lab/` 中 app 管理接口与生命周期，config / models 做预检，images 处理图片，gateway 调用，store 在单线程持有 SQLite，runner 管理单活跃批次，static 提供界面。
- data 目录保存 SQLite、原图和统一处理后的图片；测试数据在 .test-data。文件与数据库一起备份。

修改需求时读取 `specs/001-model-image-compare/spec.md`；修改调度或存储时读取同目录 `data-model.md`；修改 HTTP 时读取 `contracts/http-api.md`。任务进度见 `tasks.md`，已执行验证与真实接入缺口见 `validation.md`，启动与价格配置见 README.md。

## 已确认边界

同轮 1–20 张独立图片 × 1–5 个模型，统一图片字节与最终提示词；编辑器保留 JSON 规则，prompts.render_prompt 在创建轮次时编排为分节文本，冻结 rendered_prompt_text / prompt_renderer_version，与原始 prompt_text 一起保存。所有模型和重试使用同一冻结文本；旧轮次缺少新字段时沿用原始 JSON，不重新渲染。结果和历史对比可查看实际提示词。可调整 thinking、thinking_budget、max_tokens、temperature。完整预检通过后才创建轮次；连接缺失或本地不兼容设置拒绝整轮，不静默省略或改写参数。

调用层使用 LangChain ChatOpenAI 对接 new-api / OpenAI 兼容入口，不再读取 *_PROFILE 或限制官方域名。原四模型共享连接，27B 独立且不回退。按模型槽位映射特殊参数：Qwen 使用 enable_thinking，开启时带 max_completion_tokens，可选 thinking_budget；DeepSeek/Kimi 使用 thinking.type 开关，不发送数值预算。预算仅用于 Qwen；DeepSeek 思考时不发送 temperature，Kimi temperature 固定为思考 1.0／非思考 0.6。页面明确说明这些映射，实际参数保存在尝试快照中。服务端能力和范围错误记录为调用失败，不静默改写参数。真实视觉和参数生效情况仍需验收，不能宣称五款真实模型已接通。

输出仅为 events 中的 canonical_event_code / confidence / evidence，不画框、不添加 uncertain 状态或自动准确率排行。有效空列表是“未检出”，解析或调用失败单独保留。默认提示词为 hos-analysis 全局默认模板的 22 项事件、用户提供的事件目录响应与当前初筛指令的本地快照，带来源信息；运行时不依赖生产目录，不将其中的区域/佩戴义务假设默认为用户现场事实。

模型与输入章节逐项展示事件，支持搜索、只看已选、勾选及在独立编辑区切换微调规则；完整 JSON 与单项编辑同步。当前草稿保留未选事件，创建轮次仅提交已选 events，至少选择一项。恢复默认全选；复用历史加载该轮已保存事件，不恢复当时未提交的草稿。

每个模型内部串行，最多五路；只有一个活跃执行批次。停止与认领使用同一把锁，停止只阻止未开始项；重试追加 attempt 并拥有独立 cancel_requested，不能继承旧 stop_requested。重启将 queued/running 标记 interrupted，不自动调用。创建及重试通过 request_id 去重，事务提交前不发送模型请求。

保留输入、模型身份、参数、原始响应、错误和实际用量；密钥不入快照。费用依据价格快照与实际 usage，用 Decimal 计算，缺失时为 null，不把预算当消耗、不重复加计 reasoning。历史结果不可被编辑器或重试覆盖。

数据集标注、Precision/Recall/F1、级联及报表属于后续评测方向；实现这些功能前另行明确分母、正负例、独立验证样本及成本口径。

## 开发约束

- 模型结果每次尝试右上角提供报文弹窗。Gateway 在 HTTPX request hook 捕获 SDK 最终序列化正文，request_body / request_http / response_http 与 raw_response 在尝试结束后保存；超时仍保留已捕获请求，旧记录缺失时不重建。完整正文只在 attempt 详情读取，轮次摘要排除 request_body。凭据及敏感报文头脱敏；图片 Data URL 完整保存，UI 默认折叠并支持原文和复制，阅读视图仅影响呈现。

- 事件可选 `tile_detection: bool`，缺省关闭。直接切片而非初筛后复核；处理后宽高比 ≥ 3 时采用横向三片、25% 重叠、JPEG95，其他事件使用整图，非宽图回到整图。每个图片与模型仍为一次请求，按视图分配事件并由模型在原 events 协议内汇总。轮次 `image_detection_inputs` 冻结逐图视图和最终提示词；重试不重新编排。页面事件列表每行右侧提供无文字分割图标切换按钮（无需打开编辑区，全选/清空选择不改变切片设置），与 JSON 同步、历史可复用，恢复默认关闭，切片开关与只看已选状态在当前站点 localStorage 保存，刷新恢复，恢复默认重置。多图真实能力仍待验收。

- 使用中文沟通和编写项目说明；Git 提交信息使用中文，未经请求不提交或推送。
- 生成 Git commit message 前，必须读取并遵循 [Git 提交规则](GIT_COMMIT_RULES.md)。
- 先说明假设和验收标准；需求歧义影响实现时先澄清。
- 使用满足当前需求的最小实现，不增加未请求的功能、依赖或扩展架构。
- 修改前读取相关代码；只改任务必要文件，保留用户未提交工作，不顺手重构。
- 新增逻辑与修复缺陷应做针对性验证；仅文档变更无需引入测试框架。区分本地测试、真实 API 调用和端到端验证，未运行的检查不能报告为通过。
- 不把 API 密钥、敏感样本或含凭据的响应提交到仓库；接入真实模型时使用环境配置，并避免默认测试触发付费调用。
- 随项目实际实现更新本文件中的结构和命令，避免将规划写成已完成功能。

连接配置：原四个模型共用 `VLM_BASE_URL` / `VLM_API_KEY`；`qwen3.6-27b` 独立使用 `QWEN36_27B_BASE_URL` / `QWEN36_27B_API_KEY`。各模型 ID 和价格独立配置；BASE_URL 包含服务路径前缀，程序追加 `/chat/completions`。

界面日期时间统一使用 Asia/Shanghai 时区与中文年月日、24 小时制（YYYY年MM月DD日 HH:mm:ss），不依赖浏览器语言或本机时区。存储与原始响应时间保持原始协议值。

本轮检测事件的勾选状态按事件编码保存在当前站点的浏览器 localStorage，刷新后恢复（包括空选择）；恢复默认会保存全选状态。此设置不跨浏览器同步，不保存规则文本修改。
