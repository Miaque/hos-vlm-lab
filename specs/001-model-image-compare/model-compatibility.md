# 当前接入方式（2026-09-12）

用户确认改用 LangChain ChatOpenAI 对接 new-api，并保留 27B 的独立连接。本节替代下方历史调查中的 PROFILE/官方域名放行限制；历史文档不作为网关能力证明。

不再读取 *_PROFILE。按槽位映射：Qwen 非思考发送 enable_thinking=false/max_tokens；开启发送 enable_thinking=true/thinking_budget/max_completion_tokens。DeepSeek/Kimi 发送 thinking.type=disabled/max_tokens，数值思考预算暂拒绝。温度原样传递；未知服务端范围不在本地虚构上限，实际不兼容由调用错误保留。27B 目前采用同一 Qwen 请求形式，独立部署是否支持须真实验证。

调用配置依据：[LangChain ChatOpenAI](https://docs.langchain.com/oss/python/integrations/chat/openai)、[extra_body](https://reference.langchain.com/python/langchain-openai/chat_models/base/BaseChatOpenAI/extra_body)、[Qwen 思考参数](https://help.aliyun.com/en/model-studio/deep-thinking)。不自动重试；捕获 SDK 解析前原始响应，保留扩展 usage。T030/T033 真实服务验收仍未完成。

---

# 四模型参数兼容性核实

核实日期：2026-09-11。范围：官方公开文档；未读取密钥、未调用付费推理 API。下表按 **DeepSeek 官方、Qwen 百炼、Kimi 官方直连** 建立设计基线；实际环境变量若指向第三方网关，必须另行核实，不能沿用品牌推断。

## 结论与矩阵

四款模型均有官方视觉输入依据，但四项控制并非都能按同一个数值生效。建议四模型首次比较关闭思考，temperature=0.6；开启思考时按兼容性阻止不支持当前设置的模型，不静默省略或改值。

| 模型／服务 | 官方 model ID 与图片 | 思考开关 | THINKING_BUDGET | MAX_TOKENS | TEMPERATURE |
| --- | --- | --- | --- | --- | --- |
| DeepSeek 官方 V4.1 Flash | `deepseek-flash`，支持视觉 [D1][D3] | `thinking.type=enabled/disabled`，默认开 [D2] | 未发现数值预算契约；只有 reasoning_effort 档位，不能等同 token 预算 [D2][D4] | `max_tokens` 支持；总生成上限，仍受上下文约束 [D4] | 非思考 0–2；思考时接受但无效 [D2][D4] |
| 百炼 Qwen3.6 Flash | `qwen3.6-flash`，图像输入 [Q1] | `enable_thinking` [Q3] | `thinking_budget`，约束思考 token [Q3] | 建议映射 `max_completion_tokens` 为思考+回答总上限；旧 `max_tokens` 仅回答 [Q3] | [0,2)，思考默认0.6、非思考默认0.7 [Q3] |
| 百炼 Qwen3.8 Flash | `qwen3.8-flash`，原生多模态 [Q2] | `enable_thinking`；文档也允许 effort=none 映射关闭 [Q3][Q4] | 支持，与 reasoning_effort 互斥；预算还会映射力度档位 [Q3] | 同上 [Q3] | [0,2)；思考视觉默认0.6，低于0.6被服务端提升为0.6 [Q3] |
| Moonshot 官方 Kimi 2.6 | `kimi-k2.6`，图像 Base64 输入 [K1] | `thinking.type=enabled/disabled`，默认开 [K1] | 未发现数值预算契约，K2.6 不支持 reasoning_effort [K2][K3] | 专属页支持 `max_tokens`，默认32768 [K1]；总量语义见下述待核项 | 思考固定1.0；非思考固定0.6；其他值报错 [K1] |

## 必须落实到设计的约束

1. 能力表键为服务商／端点配置与模型 ID。百炼托管 Kimi 明确支持 `thinking_budget`，这不证明 Moonshot 官方直连支持；第三方网关也可能修改参数语义。[Q3][Q4][K2]
2. 用户设置值、实际发送字段与值、文档规定的生效语义分开记录。DeepSeek 思考时设置 temperature 必须被预检拒绝；Qwen3.8 思考时 temperature<0.6 必须拒绝；Kimi 不符合对应固定温度时必须拒绝。不能在后端偷偷改成合法值。
3. 关闭思考时预算字段禁用且不发送。预算留空在接口层意味着不要求数值预算，不等于0；但本版严格比较不提供此放宽选项，开启思考需填写受支持预算，因此DeepSeek官方及Moonshot官方K2.6不能参加该组设置。
4. 页面 `MAX_TOKENS` 建议解释为总生成预算，并在请求预览显示供应商字段名。百炼有专门总量字段，不能将其旧 `max_tokens` 与别家的同名字段直接视为等价。Moonshot K2.6 总量语义未获明确模型专属证据前，不声称思考模式严格预算可比。
5. 统一客户端发送的图片字节、尺寸及哈希；服务商内部缩放和视觉 tokenization 仍不同。不能宣称模型实际看到了完全相同的内部张量。[Q3][K1]

## 最新文档、冲突与尚待证据

- DeepSeek 2026-09-10 发布公告要求 `deepseek-flash`；旧 `deepseek-v4-flash` 与 `deepseek-v4-flash-vision-exp` 已路由到新版本。此次直接打开无查询参数的 API 文档也已更新为 V4.1，旧搜索缓存仍显示 V4，不能使用缓存判断当前版本。[D1][D3]
- DeepSeek 当前定价页列 1M 上下文、384K 最大输出；不能把这个产品上限当实验默认值。其价格有缓存命中和峰谷差异，费用计算须另存价格来源、时段与 usage 分类。[D3]
- 百炼 Qwen3.8 文档有明确预算到力度映射（<=4096 / <=16384 / 更大档），但默认预算叙述与通用“默认最大思维链长度”并不完全一致。实现应显式记录请求预算；不要将力度档位反向伪造成用户预算。[Q3]
- Qwen 两款当前产品页未给出可直接验证的模型专属最大输出／最大思考预算数字；本次不填推测硬上限。接入时按实际地域的模型列表补充能力配置，处于已核实范围且语义兼容才允许预检放行。
- Kimi 通用 Chat API 页面默认渲染 K3，并将 `max_tokens` 标为弃用；K2.6 专属快速开始仍使用 `max_tokens`。不能将 K3 上限或新参数直接复制给 K2.6。K2.6 的绝对输出上限、思考是否计入该上限、是否正式支持 `max_completion_tokens` 仍需模型专属契约或受控调用证据。[K1][K3]
- 官方文档支持不等于用户账号／地域／网关已开通。本报告不提供真实连通性、计费或协议返回成功的保证；需要后续显式真实 API 验证。

## 官方来源

- [D1 — DeepSeek V4.1 Flash 发布公告](https://www.deepseek.com/en/news/deepseek-v4-1-flash/)
- [D2 — DeepSeek Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/)
- [D3 — DeepSeek Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/)
- [D4 — DeepSeek Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)
- [Q1 — 百炼 qwen3.6-flash 模型信息](https://help.aliyun.com/zh/model-studio/qwen3-6-flash)
- [Q2 — 百炼 qwen3.8-flash 模型信息](https://help.aliyun.com/zh/model-studio/qwen3-8-flash)
- [Q3 — 百炼 OpenAI 兼容 Chat 参数](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions)
- [Q4 — 百炼视觉推理用法](https://help.aliyun.com/en/model-studio/visual-reasoning)
- [K1 — Kimi K2.6 专属快速开始及参数差异](https://platform.kimi.ai/docs/guide/kimi-k2-6-quickstart)
- [K2 — Kimi Thinking Models](https://platform.kimi.ai/docs/guide/use-thinking-models)
- [K3 — Kimi Chat Completions API](https://platform.kimi.ai/docs/api/chat)


## 2026-09-11 实现核对

直接复核 [D4](https://api-docs.deepseek.com/api/create-chat-completion/)：`max_tokens` 明确为 1–393216（384K），非思考 `temperature` 为 0–2，思考时温度无效。实现仅放行官方 `deepseek-flash`、完整 `/chat/completions` 或 `/v1/chat/completions` 端点、非思考配置。

Qwen36/Qwen38/Kimi 的环境槽位已实现，但不因设置 PROFILE 就绕过缺失范围证据。实际服务商/地域/端点仍未提供；没有读取其他项目密钥，也没有进行真实调用。T030（实际接入取证）和 T033（真实验收）保持未完成。

## 新增 Qwen3.6 27B（2026-09-11）

用户新增第五个模型 `qwen3.6-27b`，使用独立 base_url 与 api_key。配置槽位 `qwen36_27b` 已实现；实际提供方、完整地址、视觉输入能力及四项参数范围尚待取证，不沿用 Qwen Flash 的能力或密钥，当前预检保持拒绝运行。以上官方调查仅覆盖原四款，不是 27B 的接入证据。T030/T033 的后续范围扩为五款，真实三图验收应产生 15 个组合。
