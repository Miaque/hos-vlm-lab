# 本地HTTP与页面契约

仅127.0.0.1:8000同源页面；无跨域写入，校验Host及浏览器Origin，原文当文本渲染。模型连接来自环境变量，GET配置仅返回是否齐全和能力，不返回密钥。

## 公共类型

- controls = {thinking: boolean, thinking_budget: positive integer|null, max_tokens: positive integer, temperature: finite number}。关闭思考预算必须null；开启时预算可为null，填写时必须小于max_tokens，仅发送给Qwen。所有模型支持思考开关映射；DeepSeek思考时不发送temperature，Kimi固定使用思考1.0／非思考0.6，其余使用输入值。temperature输入为0–2，实际参数保存在attempt中。
- error = {code: string, message: string, details: [{model_key?: string, field?: string, message: string}]}。
- request_id为客户端每次操作生成的UUID；同请求重传必须复用ID，修改内容必须换ID。
- status值见[data-model.md](../data-model.md)。所有用量、费用的null显示未知；无模型结果显示未运行，不显示未检出。

## 路由

| 请求 | 输入 | 成功响应 |
| --- | --- | --- |
| GET /api/config | 无 | 200 {models:[{key,label,configured,runnable,reason,capabilities}],default_prompt,limits} |
| POST /api/images | multipart files，1–20静态图片 | 201 {images:[{id,name,original_url,prepared_url,width,height,prepared_sha256}]} |
| GET /api/images/{id}/{variant} | variant=original或prepared | 200图片；仅读取登记文件 |
| POST /api/rounds | {request_id,image_ids,model_keys,prompt_text,controls} | 202 {round_id}，同ID同内容返回相同轮次 |
| GET /api/rounds | limit默认20最大100，offset非负默认0 | 200 {items:[{id,created_at,status,counts}],total} |
| GET /api/rounds/{id} | 无 | 200 {id,status,counts,images,model_snapshot,prompt_text,rendered_prompt_text,prompt_renderer_version,event_snapshot,controls,attempts:[摘要]}；旧轮次无两个编排字段 |
| GET /api/attempts/{id} | 无 | 200完整attempt明细，包括原始响应、参数、事件、error、usage、pricing、cost、currency |
| POST /api/rounds/{id}/stop | 无 | 200 {round_id,status,counts}，停止当前活动执行批次，无活动批次时不改变历史；重复停止安全 |
| POST /api/attempts/{id}/retry | {request_id} | 202 {round_id,attempt_id}，同ID同目标返回相同attempt |

attempt摘要包含id、image_id、model_key、attempt_no、retry_of、status、elapsed_ms、事件摘要和费用，不包含完整原文。按尝试顺序展示，不能仅保留重试后的成功。

## 输入与错误

创建轮次整体校验：image_ids必须包含1–20个图片ID，ID存在且不重复、模型1–5款且不重复、所有配置兼容；完整JSON提示词根对象包含非空events，其code/name非空且code唯一，输入事件判定字段保留。创建时生成分节文本 rendered_prompt_text 并与原始 prompt_text、prompt_renderer_version 一起提交快照。全部模型发送同一冻结文本，重试不重新编排；旧轮次缺少该字段时仍发送 prompt_text。request_id 幂等比较以用户输入为准，不受编排版本变化影响。

轮次数量限制独立于单次上传限制：分批上传后合并21个有效ID创建轮次也必须返回422，details.field为image_ids，不创建轮次或尝试、不发起模型调用；1个和20个有效ID均允许进入后续校验。

上传任何文件不合法时本次上传整体失败，不创建部分有效图片组；已写临时文件清理。单图10MiB、2000万像素，静态JPEG/PNG/WebP。数据路径不接受用户任意目录。

422输入或参数无效；413上传限制；404记录缺失；409有活动批次、重试身份变化、request_id内容冲突或目标不可重试。可重试状态仅failed/invalid_response/interrupted。本地不支持的参数组合为422；服务商能力与范围错误在实际调用后记入attempt。

已接纳后模型HTTP错误、超时和格式错误写入attempt，不改变创建轮次202语义。没有自动格式纠正或请求重试。

## 页面交互

工作台左侧图片组与预览，右侧模型、四项参数、完整提示词。下方按当前图片展示各模型卡片，折叠原文和实际参数。每秒刷新活动轮次摘要，终态停止轮询。刷新页面后可从历史恢复活动轮次。

历史视图选两轮按image_id对照；重传同内容不同ID可以根据原图及处理后哈希对应，预处理不同则明确标注。对应模型缺失显示未运行。恢复默认不覆盖历史；正在运行时编辑仅用于下一轮。

原四模型共用 VLM_BASE_URL / VLM_API_KEY；BASE_URL 包含服务路径前缀，程序追加 /chat/completions。DEEPSEEK/QWEN36/QWEN38/KIMI 前缀保留 _MODEL_ID 和可选 _PRICING_JSON，各模型旧 _API_URL / _API_KEY 不再读取；不读取 PROFILE。价格未配置显示未知，不要求用户填虚构费用。


新增模型 key 为 `qwen36_27b`，使用独立 `QWEN36_27B_BASE_URL` / `_API_KEY` / `_MODEL_ID`，可选 `_PRICING_JSON`；BASE_URL 包含服务路径前缀，追加 `/chat/completions` 得到快照中的 api_url。没有共享 VLM 配置回退。

当前 capabilities 返回 adapter=langchain-openai、strict_validation=false；controls 仅描述本地参数映射，不代表服务商已验证能力。max_tokens 不返回未经验证的服务商上限。
