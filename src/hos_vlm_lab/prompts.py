"""将编辑用 JSON 编排为可冻结、可追溯的模型输入文本。"""

import json

from .models import _json


PROMPT_RENDERER_VERSION = "2026-09-12.v1"


def render_prompt(text: str) -> str:
    data = _json(text)  # 调用前由 RoundRequest 校验 events 身份。

    def display(value):
        return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)

    sections = [
        "# 任务\n" + display(data.get("task", "检测当前图片中符合下列定义的事件。")),
        "# 判定原则\n"
        "仅依据当前单张图片中的直接可见证据，逐项独立判断。先确认目标，再核对命中条件、排除条件和证据不足规则。\n"
        "事件名称和编码只是类别，不是事件成立的证据；不得由场景常识补全不可见细节或推断单帧无法证明的时间过程。\n"
        "证据不足时不返回该事件；uncertain 表示不命中的规则，不是输出状态。不要输出逐项分析过程。",
    ]
    if "instructions" in data:
        rules = data["instructions"]
        content = "\n".join(f"- {display(rule)}" for rule in rules) if isinstance(rules, list) else display(rules)
        sections.append("# 通用要求\n" + content)
    events = []
    labels = {"match": "命中条件", "exclude": "排除条件", "uncertain": "证据不足时"}
    for event in data["events"]:
        lines = [f"## {event['name']}", f"事件编码：{event['code']}"]
        for key, value in event.items():
            if key not in {"code", "name", "tile_detection"}:
                lines.append(f"{labels.get(key, key)}：{display(value)}")
        events.append("\n".join(lines))
    sections.append("# 待检测事件\n" + "\n\n".join(events))
    # 只省略已知的追溯/格式元数据；用户自定义上下文不得静默丢失。
    extra = {key: value for key, value in data.items() if key not in {
        "source", "format_version", "field_guide", "task", "instructions", "events", "output"
    }}
    if extra:
        sections.append("# 补充上下文\n" + display(extra))
    output = (
        "# 输出\n"
        "只输出一个 JSON 对象，顶层只有 events 数组，不要 Markdown、坐标或额外文字。\n"
        "每个命中项仅含 canonical_event_code、confidence、evidence：编码必须来自上述目录，且每个编码最多一次；"
        "confidence 为 0 到 1 的数字；evidence 为非空中文可见证据，描述位置、目标特征或行为，最多 200 字。\n"
        '没有事件满足条件时返回 {"events":[]}。\n'
        "提交前核对编码、字段和可见证据是否一致，只提交最终 JSON。"
    )
    if "output" in data:
        output += "\n以下 output 仅为结构示意，必须替换占位文字及示例数值，不代表本图存在事件：\n" + display(data["output"])
    sections.append(output)
    return "\n\n".join(sections)


def render_view_prompt(prompt: str, views: list[dict]) -> str:
    return prompt + (
        "\n\n# 本次图像视图分配（优先于通用的单图说明）\n"
        "下列图像均来自同一张图片，顺序与视图列表一致；每个事件仅使用 event_codes 指定的视图。\n"
        "full 是整图；T0、T1、T2 是由左至右、相邻重叠约 25% 的全高切片，坐标基于处理后图片。\n"
        "切片直接检测，不等待整图初筛；逐片独立判断，不跨片拼凑证据。"
        "证据被切片边界截断、关键关系延伸到片外或需要猜测片外内容时不命中。\n"
        "同一事件多片命中时只返回置信度最高的一项，evidence 注明视图编号；未命中则不返回。"
        "仍严格使用上述 events 输出结构。\n"
        + json.dumps(views, ensure_ascii=False)
    )
