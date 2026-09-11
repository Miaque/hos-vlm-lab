# 数据模型

本文件定义拟实现结构，尚未建库。UUID字符串作为业务ID；UTC时间持久化，页面按本地时区显示。JSON快照保留当次含义，不随配置更新覆盖。

| 实体 | 必填字段 | 可空字段与约束 |
| --- | --- | --- |
| images | id, original_name, original_sha256, prepared_sha256, original_path, prepared_path, width, height, preprocessing_version, created_at | 路径为data目录下生成的相对路径，不使用上传文件名拼路径 |
| rounds | id, request_id, request_hash, prompt_text, event_snapshot, model_snapshot, controls, stop_requested, created_at | request_id唯一，同ID不同内容报冲突 |
| round_images | round_id, image_id, position | 外键有效，(round_id,image_id)唯一；保持上传顺序 |
| attempts | id, round_id, image_id, model_key, attempt_no, request_parameters, status, created_at | retry_of、retry_request_id、started_at、finished_at、elapsed_ms、raw_response、parsed_events、error、usage、pricing、cost、currency可空 |

attempts唯一键为(round_id,image_id,model_key,attempt_no)，retry_request_id有值时唯一；retry_of指向同图同模型旧尝试。密钥不在任何快照中。原始HTTP正文和模型正文分别可追溯，脱敏凭据；HTTP失败也可保留正文。

## 状态

queued → running → succeeded / invalid_response / failed。
queued → stopped；进程重启发现queued/running → interrupted。

轮次状态按以下顺序汇总，counts始终包含全部历史尝试，completed不代表全部成功：

1. 当前执行批次有queued/running项，且该批次尚未请求停止：running，包括刚接纳尚未开始的重试。
2. 当前批次已请求停止且仍有running项：stopping。
3. 没有活动项：历史中存在stopped尝试则stopped，否则completed。历史failed/interrupted保留在counts，不自动视为成功。

rounds.stop_requested仅记录本轮曾收到停止，不再作为新重试批次的调度门禁。每次新执行批次在内存中持有独立cancel_requested=false和所属attempt IDs；停止只更新当前批次并保留历史标记。所有queued/running在重启时变为interrupted，因此无需持久化活动批次来自动恢复调用。

例如：首轮有failed和stopped项，终态为stopped；重试failed项后显示running，旧停止标记不令其变成stopping；重试结束后仍显示stopped，因为历史未执行项仍保留。若停止重试，排空在途项后也回到上述终态规则。无活动批次的停止请求不改变历史结果。

停止标志与领取下一项使用同一同步边界。重试追加新attempt，不复活旧attempt；单次重试执行许可与原轮stop标志分开，重试自身可被停止。全局仅一个活动执行批次，避免重试绕过并发限制。

## 一致性

- 图片先写临时文件并原子重命名，再写元数据；失败可留下无引用文件但不能留下有效记录指向未写完文件。
- 创建round、关联图片、全部attempt在一次事务提交，提交后才调度。
- request_id相同且内容相同返回原记录，不再次调用；不同内容409。重试也遵循此规则。
- 执行中修改编辑器不影响快照。重试使用原身份与参数，配置身份变化时409，密钥可以更新。
- 数据库故障导致终态无法写入时停止新增调度；重启后按中断处理，不自动重复远端调用。

## 协议与计费

controls：thinking为boolean，temperature有限数值且必填，max_tokens正整数且必填；thinking=true要求thinking_budget正整数，false要求null。进一步按profile约束校验，不把bool当整数。

events输出根对象只含events列表。每项仅canonical_event_code、confidence、evidence；编码属于本轮且唯一，confidence为有限0–1数字，evidence去空白后非空且原始长度不超过200。保留原文，解析失败不修正。

usage保留原始结构，另保存归一化input/output/reasoning/cache用量，可未知。pricing保存币种、各类单价、生效时间/时段与来源。Decimal计算并以十进制字符串保存费用；reasoning已包含在output时不重复加算。必要用量或价格缺失则cost=null；不从MAX_TOKENS或budget估算实际消耗。

