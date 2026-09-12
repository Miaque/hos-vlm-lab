# hos-vlm-lab

本机多模态图片对比工作台：上传 1–20 张图片，选择模型，修改完整 JSON 提示词，在相同输入与可比参数下逐图检测，查看结果、原始响应与历史对照。不画框，不自动重试，不生成准确率排名。

## 启动

需要 Python 3.12+ 和 uv，在仓库根目录执行：

```powershell
uv sync --group dev
uv run hos-vlm-lab
```

打开 http://127.0.0.1:8000 。入口绑定本机、单进程。启动时自动加载当前工作目录的 `.env`，已有环境变量优先，文件不存在时跳过；修改后重启。没有配置模型也可以查看页面，无法提交真实检测。

无需密钥体验完整交互（仅模拟，不发生模型费用）：

```powershell
uv run python -m tests.browser_app --data-dir .test-data/browser
```

打开 http://127.0.0.1:8001 。页面与模型名称标明“模拟”；四个测试模型分别返回检出、空结果、失败与慢响应。该入口位于 tests，不打包进正式应用；拒绝出站网络。省略 `--data-dir` 使用退出即清理的临时目录；指定目录只能位于仓库 `.test-data` 下，保留历史供下次启动查看。

## 模型配置与当前接入边界

模型输出支持纯 JSON，以及外层单反引号或三反引号代码块（可带 json 标签）；去除外层标记后仍严格校验事件协议，原始响应保持不变。

模型请求关闭 TLS 证书校验，适用于当前本机网关调试；HTTPS 仍加密，但不验证服务端证书身份。

使用 [.env.example](.env.example) 配置连接。调用层使用 LangChain `ChatOpenAI`，支持 new-api 的 OpenAI 兼容 Chat Completions 入口，不限制官方域名。无需填写 `*_PROFILE`，旧变量不再读取。

| 模型 | 连接变量 |
| --- | --- |
| DeepSeek、Qwen3.6 Flash、Qwen3.8 Flash、Kimi | `VLM_BASE_URL` / `VLM_API_KEY` |
| Qwen3.6 27B | `QWEN36_27B_BASE_URL` / `QWEN36_27B_API_KEY`，不回退到共享连接 |

BASE_URL 包含服务路径前缀（例如 `https://your-host/v1`），不含 `/chat/completions`。每款模型独立填写 `_MODEL_ID`，使用网关中实际可用的名称；价格 `_PRICING_JSON` 可选。修改后重启。在仓库根目录配置 `.env` 后直接启动：

```powershell
uv run hos-vlm-lab
```

参数按模型槽位适配，模型 ID 保持环境配置值。所有模型都支持本地思考开关映射。Qwen 三个槽位发送 `enable_thinking`；开启时发送 `max_completion_tokens`，预算填写时才发送 `thinking_budget`；关闭时发送 `max_tokens` 且不发送预算。DeepSeek/Kimi 发送 `thinking.type=enabled/disabled` 和 `max_tokens`，不发送数值预算。预算仅用于 Qwen，留空使用服务端默认。DeepSeek 思考时不发送温度，Kimi 温度固定为思考 1.0／非思考 0.6，其余原样传递；页面明确显示映射，实际参数保存在尝试快照。温度输入本地校验 0–2；输出及已填写预算必须为正整数，预算小于输出上限。

连接齐全即可进行非思考请求，不再因缺少服务商范围证明阻止调用。实际视觉能力、参数范围与生效语义由配置的网关和上游决定；特别是独立部署的 27B 需支持上述 Qwen 参数形式，否则保存其调用错误并按实际服务适配。服务商限制导致的 HTTP 错误保存在单项结果，不静默修改设置。

LangChain 自动重试和本次调用的 LangSmith tracing 均关闭。原始响应在 SDK 解析前捕获并脱敏，保留供应商扩展字段、实际 usage 和错误；费用计算与历史存储不变。**本地模拟测试不代表五款真实模型已接通，也不证明各服务的预算语义完全可比。** 历史官方调查与当前接入说明见 [能力调查](specs/001-model-image-compare/model-compatibility.md)。

## 使用流程

1. 上传图片组，查看统一处理后的预览；也可切换原图。支持静态 JPEG/PNG/WebP，单图 ≤10 MiB、解码 ≤2000 万像素。统一 EXIF 方向、透明背景转白、RGB、最长边 2048（不放大）、JPEG quality=90。
2. 选择模型，编辑 JSON 检测规则。输入 `events` 中的 `code`/`name` 决定本轮事件身份；创建轮次时转换为“任务、判定原则、通用要求、事件定义、输出”的分节文本，所有模型收到相同文本。结果区可展开“本轮实际发送的提示词”。原 JSON 与最终文本一起冻结，不增加隐藏 system 消息。
3. 开始对比，点击图片缩略图查看各模型结果。单图×单模型是一次独立尝试；最多五路，每个模型内部串行。运行时编辑仅用于下一轮。
4. 在历史中复用输入、调整提示词后新建轮次；选择 A/B 对照。按图片原始哈希对应，预处理差异明确提示；没有运行的模型显示“未运行”。
5. 停止仅停止待开始项，已发出的请求允许结束。失败/解析失败/中断可单项手动重试，新增尝试编号并保留旧结果。重启后未完成项标记中断，不自动调用模型。连接身份改变时拒绝旧轮次重试。

模型输出协议固定为：

```json
{"events":[{"canonical_event_code":"person","confidence":0.9,"evidence":"画面左侧可见站立人员"}]}
```

每项只允许这三个字段；编码须属于本轮且不重复，置信度为有限 0–1 数字，证据非空且不超过 200 字。`{"events":[]}` 表示未检出，不代表确认不存在。空对象、格式错误、截断、超时和 HTTP 错误均单独记录。

默认提示词为 2026-09-12 同步的本地快照：事件范围来自 `hos-analysis` 当前配置数据库的全局默认模板，共 22 项；判定条件来自用户提供的事件目录接口响应（34 项均可用），通用指令与输出结构来自当前 `QwenScreeningClient`。来源版本记录在提示词中。模板包含动物检测，不包含汽车基础检测；租户自定义场景可能不同。程序运行不依赖数据库、事件目录或其他仓库，后续源数据变化不会自动同步。

### Qwen 提示词格式

核对日期：2026-09-12。Qwen 的 OpenAI 兼容视觉接口使用 `messages`，在用户消息的 `content` 中传入 `text` 和 `image_url`；本项目已按此格式发送，图片使用 JPEG data URL。参考[官方视觉接口](https://www.alibabacloud.com/help/zh/model-studio/vision)和 [Qwen3.6-27B 模型卡](https://huggingface.co/Qwen/Qwen3.6-27B)。网关中的模型名称不证明其上游部署与官方服务完全一致。

提示词正文可以使用自然语言，也可以用 JSON 组织自然语言规则；JSON 不是 Qwen 专用提示词格式。本项目保留 JSON 编辑规则，发送前由 `prompts.render_prompt` 编排分节文本，完整保留事件定义、用户指令和自定义上下文，仅省略 `source`、`format_version`、`field_guide` 追溯/格式元数据。输出仍要求 JSON。原始 JSON 和最终文本分别保存为 `prompt_text` / `rendered_prompt_text`，`prompt_renderer_version` 标识编排版本。创建后编辑、重试或升级程序均不改变冻结文本；旧轮次重试仍发送原始 JSON。重启服务并刷新页面后，新建轮次使用文本编排。参考[官方提示工程指南](https://help.aliyun.com/zh/model-studio/prompt-engineering-guide)。

输入使用 JSON 不等于启用 JSON Mode。当前仅通过提示词要求 JSON 输出，并在本地严格解析。官方另有 `response_format` 结构化输出参数，但支持范围与思考模式有关，独立部署还取决于服务端实现；本次未自动添加该参数。详见[官方结构化输出说明](https://help.aliyun.com/zh/model-studio/qwen-structured-output)。本次真实对比结果与限制见 [提示词验证记录](specs/001-model-image-compare/prompt-format-validation.md)。

## 存储与费用

默认目录为 `data`，可用 `VLM_DATA_DIR` 指定。SQLite 保存图片身份、Prompt、模型与参数快照、每次响应/错误/用量；原图和实际发送的图片另存文件。上传源文件移走不影响历史。运行目录与密钥文件已忽略，备份时一起保存 SQLite 和 images 目录。

价格参考源采用 [LiteLLM 模型价格目录](https://cdn.jsdelivr.net/gh/BerriAI/litellm@main/model_prices_and_context_window.json)。默认按官方提供方前缀与模型标识匹配：DeepSeek 使用 `deepseek/`、Qwen 使用 `dashscope/`、Kimi 使用 `moonshot/`。官方条目缺失时回退到 `openrouter/<厂商>/<同名模型>`，并在价格快照的 `catalog_key` 中保留来源；两者都缺失时价格保持未知；当前使用手动获取的价格快照，程序不会自动联网同步。

费用是根据用户价格配置和实际 usage 计算的估算，不是账单。可选 `<前缀>_PRICING_JSON`，结构如下（数字仅为演示）：

```json
{"currency":"CNY","source":"示例，替换为价格来源","valid_from":"2026-09-01T00:00:00+08:00","valid_until":"2026-10-01T00:00:00+08:00","input_per_million":"2","output_per_million":"8","cache_read_per_million":"0.2"}
```

单价用十进制字符串，单位为每百万 token；输入价按未命中缓存的部分计算，输出价包含思考，不重复加算 reasoning。省略缓存价表示全输入按统一价格；配置缓存价但缺缓存用量时费用未知。时间区间为左闭右开，须带时区；仅支持这一个明确有效区间，不自动推断峰谷规则。缺来源、币种、必要单价/用量，或调用时间不在区间内时显示未知。每轮保存价格快照，修改当前价格不重写旧记录。

## 验证与结构

```powershell
uv run pytest -q
uv build
```

测试使用临时目录、fake 网关与 HTTPX MockTransport，不加载真实连接，不默认发起付费调用。浏览器验收及未完成的真实验收见 [validation.md](specs/001-model-image-compare/validation.md)。

`src/hos_vlm_lab` 中：`app.py` 提供 HTTP/资源生命周期，`config.py` 校验连接与参数，`models.py` 定义契约，`images.py` 处理图片，`gateway.py` 发送首次请求并处理用量，`store.py` 在独立线程持有 SQLite，`runner.py` 调度，`static/` 提供无构建链的页面。

### Qwen3.6 27B 独立连接

使用 `QWEN36_27B_BASE_URL`（含服务要求的路径前缀，例如 `https://your-host/v1`，不含 `/chat/completions`）和 `QWEN36_27B_API_KEY`；程序去掉末尾斜杠并追加 `/chat/completions`。模型标识使用 `QWEN36_27B_MODEL_ID=qwen3.6-27b`，价格可选 `QWEN36_27B_PRICING_JSON`。不读取共享 VLM 连接作为回退，缺失配置明确拒绝。无需填写 PROFILE。
