# hos-vlm-lab

本机多模态图片对比工作台：上传 1–20 张图片，选择模型，修改完整 JSON 提示词，在相同输入与可比参数下逐图检测，查看结果、原始响应与历史对照。不画框，不自动重试，不生成准确率排名。

## 启动

需要 Python 3.12+ 和 uv，在仓库根目录执行：

```powershell
uv sync --group dev
uv run hos-vlm-lab
```

打开 http://127.0.0.1:8000 。入口绑定本机、单进程。环境变量在启动时读取，修改后重启；程序不会自动加载 `.env`。没有配置模型也可以查看页面，无法提交真实检测。

无需密钥体验完整交互（仅模拟，不发生模型费用）：

```powershell
uv run python -m tests.browser_app --data-dir .test-data/browser
```

打开 http://127.0.0.1:8001 。页面与模型名称标明“模拟”；四个测试模型分别返回检出、空结果、失败与慢响应。该入口位于 tests，不打包进正式应用；拒绝出站网络。省略 `--data-dir` 使用退出即清理的临时目录；指定目录只能位于仓库 `.test-data` 下，保留历史供下次启动查看。

## 模型配置与当前接入边界

使用 [.env.example](.env.example) 中的环境变量名称。原四个模型共用 `VLM_BASE_URL` 和 `VLM_API_KEY`。BASE_URL 包含服务要求的路径前缀（例如 `https://your-host/v1`），不含 `/chat/completions`，程序自动追加该路径。各模型仍通过 `DEEPSEEK`、`QWEN36`、`QWEN38`、`KIMI` 前缀分别配置 `_MODEL_ID`、`_PROFILE` 和可选 `_PRICING_JSON`。旧的各模型 `_API_URL` / `_API_KEY` 不再读取。共享端点的能力需按实际服务核实。

| 配置 | 当前可运行范围 |
| --- | --- |
| DeepSeek 官方，profile=`deepseek`，model=`deepseek-flash` | 完整端点为 `https://api.deepseek.com/chat/completions` 或其 `/v1/chat/completions` 路径；仅非思考，temperature 0–2，总输出 1–393216 |
| Qwen3.6 / Qwen3.8 Flash | 环境配置及页面槽位已实现；实际地域与模型输出/预算上限未确证，保持不可运行 |
| Moonshot 官方 Kimi K2.6 | 环境配置及页面槽位已实现；模型专属输出上限未确证，保持不可运行 |
| Qwen3.6 27B | 独立连接槽位已实现；实际端点及视觉/参数能力待确证，保持不可运行 |
| 第三方网关 | 尚无已取证 profile，不套用官方能力 |

这些是客户端预检能力，**没有执行真实 API 验收**。五款真实模型同图对比仍需补齐服务商/地域/端点证据与合法配置。详见 [能力调查](specs/001-model-image-compare/model-compatibility.md)。

思考关闭时 THINKING_BUDGET 为空且不发送；开启时要求正整数预算，并小于 MAX_TOKENS。MAX_TOKENS 指思考与回答的总生成上限。所有选择的模型须支持用户设置；一个不兼容即拒绝整轮，不修改温度、不丢弃预算。DeepSeek 官方思考模式不能满足本实验的数值预算及温度比较条件，因此拒绝。

## 使用流程

1. 上传图片组，查看统一处理后的预览；也可切换原图。支持静态 JPEG/PNG/WebP，单图 ≤10 MiB、解码 ≤2000 万像素。统一 EXIF 方向、透明背景转白、RGB、最长边 2048（不放大）、JPEG quality=90。
2. 选择模型，编辑完整 JSON 提示词。输入 `events` 中的 `code`/`name` 决定本轮事件身份；文本逐字发送，没有隐藏 system 提示词或格式修正。
3. 开始对比，点击图片缩略图查看各模型结果。单图×单模型是一次独立尝试；最多五路，每个模型内部串行。运行时编辑仅用于下一轮。
4. 在历史中复用输入、调整提示词后新建轮次；选择 A/B 对照。按图片原始哈希对应，预处理差异明确提示；没有运行的模型显示“未运行”。
5. 停止仅停止待开始项，已发出的请求允许结束。失败/解析失败/中断可单项手动重试，新增尝试编号并保留旧结果。重启后未完成项标记中断，不自动调用模型。连接身份改变时拒绝旧轮次重试。

模型输出协议固定为：

```json
{"events":[{"canonical_event_code":"person","confidence":0.9,"evidence":"画面左侧可见站立人员"}]}
```

每项只允许这三个字段；编码须属于本轮且不重复，置信度为有限 0–1 数字，证据非空且不超过 200 字。`{"events":[]}` 表示未检出，不代表确认不存在。空对象、格式错误、截断、超时和 HTTP 错误均单独记录。

默认材料来自 `hos-analysis` 历史测试种子（源标识 `755f31a`，快照日期 2026-09-11），包含 34 个种子事件，**不代表当前生产契约或所有业务分类的最终数量**。其中受限区域、佩戴义务、宠物范围等是历史场景假设，使用前在编辑器核对。程序运行不依赖其他仓库。

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

使用 `QWEN36_27B_BASE_URL`（含服务要求的路径前缀，例如 `https://your-host/v1`，不含 `/chat/completions`）和 `QWEN36_27B_API_KEY`；程序去掉末尾斜杠并追加 `/chat/completions`。模型标识使用 `QWEN36_27B_MODEL_ID=qwen3.6-27b`，能力配置使用 `QWEN36_27B_PROFILE`，价格可选 `QWEN36_27B_PRICING_JSON`。不读取共享 VLM 连接作为回退，缺失配置明确拒绝。PROFILE 必须等待实际服务的能力取证，不能任意填写后运行。
