# 最小技术设计：多模型图片对比调试

状态：设计背景，未实现；正式计划与契约以plan.md及其关联文档为准。依据 [spec.md](spec.md)。模型接入证据见 [model-compatibility.md](model-compatibility.md)；尚未执行真实调用验证。

## 1. 技术选择

- 后端：现有 Python 3.12/uv 项目，FastAPI + Uvicorn 单进程，HTTPX 异步模型请求，Pydantic 校验。仅绑定 127.0.0.1。
- 前端：同源 HTML/CSS/原生 JavaScript；无独立构建链。当前只需上传、表单、结果卡片与历史对照，不引入前端框架。
- 持久化：标准库 sqlite3 保存结构化记录，data/images 保存原图和处理后图片。SQL 显式建表，无 ORM、外部数据库、消息队列或对象存储。
- 图片：Pillow 解码，统一 EXIF 方向、透明背景转白、RGB，长边最多 2048 且不放大，统一 JPEG quality=90；原图与实际发送文件分别留存 SHA256。页面明确显示处理后尺寸；提供方内部视觉切块无法由客户端保证一致。
- 设计默认输入上限：单图 10 MiB、解码 2000 万像素、单轮 20 图，允许静态 JPEG/PNG/WebP，拒绝动画和无法解码内容。校验在模型调用前完成，限值显示在上传区。这是本 Demo 设计上限，不是服务商能力声明。
- 不安装依赖或编写业务代码，本文件定义后续实现。

依据：FastAPI [lifespan](https://fastapi.tiangolo.com/advanced/events/) 支持共享资源生命周期；HTTPX [AsyncClient](https://www.python-httpx.org/async/) 支持异步请求及连接复用；Python 提供 [sqlite3](https://docs.python.org/3/library/sqlite3.html)；Pillow 提供 [图像解码及尺寸处理](https://pillow.readthedocs.io/en/stable/reference/Image.html)。这些工具能力来自官方文档，组合与限值为本项目设计决定。

## 2. 连接与能力配置

四组环境变量前缀：DEEPSEEK、QWEN36、QWEN38、KIMI。每组定义 API_URL（完整 chat completions 地址）、API_KEY、MODEL_ID、PROFILE；价格可选配置，未配置显示未知。API_URL 由用户可信环境配置提供，页面不能修改。敏感配置不返回浏览器。

PROFILE 绑定服务商与已经核实的模型能力，而不是根据名称包含 qwen/kimi 猜测。未知服务商或模型身份显示不可运行及原因；自定义网关不能套用官方能力后宣称已经验证。不得从其他仓库复制真实密钥。

界面值转换为服务商明确支持的字段，保存转换后的实际参数。思考预算只表示 token 预算，不能映射成不同语义的 reasoning effort 档位。模型接收但忽略的参数也属于不可比较配置。

第一版保持严格比较：temperature与MAX_TOKENS必填；开启思考时budget必须是已支持数值，关闭时为null且不发送。不指定参数的宽松比较不纳入第一版。正式契约见contracts/http-api.md。

## 3. 提示词与事件定义

### 参数调查带来的限制

按官方渠道文档，四模型可采用非思考、temperature=0.6 作为初始兼容配置候选（仍需真实端点验证）；严格思考模式下四项控制同值不存在已验证的公共交集。DeepSeek 思考温度无效，Kimi 官方思考温度固定1.0；数值预算并非所有提供方支持。

MAX_TOKENS 在本界面拟统一为总生成上限；百炼需发送 max_completion_tokens，不能套用其仅限制回答的旧 max_tokens。Kimi K2.6 思考总量语义未确证，不能宣称该模式严格预算相等。绝对上限待实际地域/端点补证，未知不填推测数值。证据详见兼容性报告。

### LangChain 取舍（已确认）

LangChain 的统一消息、invoke/stream 等接口可减少接入形式差异，但其官方文档仍明确参数支持取决于模型与服务商，不能消除固定温度、忽略温度、无数值预算等能力差异。参考 [模型接口文档](https://docs.langchain.com/oss/python/langchain/models)。

用户已确认第一版采用 HTTPX 薄调用层：共用一次请求发送和结果记录函数，提供方差异只放入参数构建与校验，不创建多级 Provider 继承体系。这里只有四款模型，必须检查实际请求和首次原始响应，增加 LangChain 仍然需要这层校验。若后续确需统一流式消息或扩展大量非兼容提供方，再评估其模型集成包；不因此引入 Agent、Chain 或 LangGraph。

如最终选 LangChain，必须关闭自动重试、显式记录最终请求字段、保留原始响应和 usage，并测试集成层没有丢弃提供方扩展信息；不能将框架标准化后的对象误称为原始 HTTP 响应。

默认提示词结构参考 hos-analysis 的 QwenScreeningClient.screen：task、events、instructions、output。事件输入项为 code/name/match/exclude/uncertain，输出遵循三个字段的 events 协议。

采用完整 JSON 文本编辑器（普通多行文本区即可），编辑后先验证根对象、events 的唯一 code/name，再原样将文本作为唯一 user 文本块发送；图片作为同一消息的 image_url 块。事件允许集合和中文名从当前文本 events 提取，而非另设会漂移的隐藏目录。不增加隐藏 system 提示词，不自动修正格式，不悄悄注入 response_format。

“恢复默认”显式替换编辑器内容；后续发送的就是用户看到的文本。空 events 输入或无效 JSON 在执行前指出。这一编辑形式是设计选择，用户仍可修改指令、排除条件及输出描述；模型未遵守固定结果契约时照实记录错误。

默认材料使用本地版本化快照。hos-analysis 当前生产目录由 Event Hub 提供，旧本地种子位于 tests/visual_event_legacy_seed.py、tests/fixtures/visual_event_seed.json，仅能作为历史预置参考，不能标为当前生产权威契约。实现时在默认材料中记录来源版本和日期，无运行时生产依赖。

## 4. 本地数据模型

| 表 | 关键内容 |
| --- | --- |
| images | id、original_sha256、prepared_sha256、原图/处理文件相对路径、原始名称、尺寸、预处理版本、created_at |
| rounds | id、client_request_id 唯一、完整 prompt_text、解析后的事件快照、模型身份与 endpoint/profile 非敏感快照、通用参数、stop_requested、created_at |
| round_images | round_id、image_id、顺序；唯一组合 |
| attempts | id、round_id、image_id、model_key、attempt_no、retry_of、实际发送参数快照、status、开始/结束时间、elapsed_ms、原始响应、parsed_events、错误分类、usage、价格快照、费用与币种 |

attempts 唯一键：(round_id,image_id,model_key,attempt_no)。状态 queued → running → succeeded/invalid_response/failed；queued → stopped；启动恢复时 queued/running → interrupted。重试追加，不将旧状态改回 queued。

使用 SQLite 外键与事务；写入封装为短事务，文件写入使用临时文件后重命名再提交元数据。事务失败可留下无引用图片但不能留下引用不存在文件的有效记录。不在本版自动清理历史文件。SQLite 工作放入单独线程串行执行，连接在该线程创建与使用；不在异步事件循环内执行可能阻塞的磁盘操作。

运行创建事务一次性写入轮次、图片关联和全部 queued 尝试；提交失败不开始模型请求。请求标识唯一，重复点击/网络重复提交返回已有轮次，不重复付费。

## 5. 运行调度

单进程、单活跃轮次（包括重试批次），每个模型最多一个在途请求；最多四路并发。各模型按图片顺序推进，慢模型不会阻塞其他模型。运行中可以编辑下一轮，但再次运行需等待当前轮结束或停止并排空在途请求。

所有执行任务由应用 lifespan 管理，客户端刷新或断开不终止已接纳轮次。前端每秒轮询当前轮次摘要，只有结果详情打开时读取原文；空闲停止轮询。

调度器在同一把短锁内检查当前执行批次的 cancel_requested 并认领 queued 项。停止在同一锁内设置当前批次标记、保留轮次曾停止标记，并将该批次其余 queued 标为 stopped，从而保证停止应答后不会发起新项。已开始请求允许结束；关闭服务则取消本地等待并标记中断，不承诺撤销服务商计费。

模型请求采用共享 HTTPX AsyncClient，连接超时 10 秒，每次调用总期限 180 秒；无自动 HTTP/格式重试。超时、429、网络错误、HTTP 非成功、响应解析错误均保留独立错误类别。失败绝不自动转成 events 空列表。

单项重试保留原轮次图片、文本、endpoint/model/profile 与参数快照，使用当前相应密钥；若环境中的连接身份已经变化则拒绝复用旧轮次，提示创建新轮。重试同样使用请求标识去重。程序重启标记中断后不自动调度。

## 6. 页面结构

一个工作台加一个历史视图：

- 左侧：本地多图上传、缩略图列表、当前原图与处理尺寸。
- 右侧：四模型勾选与配置状态、思考开关、预算、输出上限、temperature、完整提示词、恢复默认、运行/停止。
- 下方：当前图片对应的各模型卡片，状态、检出事件/证据、置信度、耗时、token、费用；原始输出和实际参数可展开。
- 历史：轮次列表，选两个轮次后按同图同模型对照；不同模型集合缺项显示“未运行”，不补成未检出。重试使用独立尝试编号。
- 参数校验错误贴近字段并汇总到对应模型；原文通过 textContent 显示，禁止当 HTML 渲染。

## 7. 本地接口

| 方法与路径 | 语义 |
| --- | --- |
| GET /api/config | 模型显示名、配置状态、能力与来源、默认提示词、输入限值；无凭据 |
| POST /api/images | 多文件上传、统一处理，返回图片身份及预览地址；无效文件明确报错 |
| GET /api/images/{id}/{original或prepared} | 只按已登记 id 访问图片，不接受任意文件路径 |
| POST /api/rounds | request_id、image_ids、model_keys、prompt_text、controls；校验成功后事务创建，202 返回 round_id |
| GET /api/rounds | 分页历史摘要 |
| GET /api/rounds/{id} | 快照、进度与尝试摘要；不附大体积原文 |
| GET /api/attempts/{id} | 输出、错误、事件、实际参数、用量与费用明细 |
| POST /api/rounds/{id}/stop | 幂等停止待开始任务 |
| POST /api/attempts/{id}/retry | request_id；只允许 failed/invalid_response/interrupted，追加尝试 |

400/422 输入与参数问题；409 已有活动轮次或连接快照不匹配；413 上传限制；404 记录缺失。模型执行失败由尝试状态表达，不让已成功接纳的创建请求无限等待。

只服务本机；写接口校验同源并禁止跨域开放，模型密钥不进入浏览器、日志和输出。模型原始业务响应保存在本地数据库供调试，HTTP 错误中若回显凭据则脱敏。运行目录和 .env 应加入忽略列表（实现阶段完成）。

## 8. 验证与交付顺序

1. 配置/能力映射与输入校验：用固定响应及请求捕获测试，证明每个字段发送/省略/拒绝符合调查证据。
2. 图片处理与事件响应协议：相同处理文件哈希；空事件、重复编码、越界数字、空证据、截断响应分别验证。
3. SQLite 轮次与尝试：创建事务、重试去重、快照不可覆盖、重启标记中断。
4. 调度器：阻塞式 fake gateway 验证停止竞争、慢模型隔离、没有自动重试及原图多模型组合数。
5. 页面：真实浏览器操作上传、错误提示、渐进结果、历史对照及刷新；不以截图代替交互验证。
6. 真实模型验证为显式选择的小样本验收，先单图单模型确认视觉与参数，再三图四模型；没有密钥或能力证据时报告未验证，不扩大调用量。

本次没有承诺功能已实现。能力文档不足不会阻止存储和页面实现，但会阻止对应配置的真实运行。


