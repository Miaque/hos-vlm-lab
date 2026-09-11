# Implementation Plan: 多模型图片对比调试

**Branch**: `master`（实际 Git 分支；本次不创建分支） | **Date**: 2026-09-11 | **Spec**: [spec.md](spec.md)

**Input**: `specs/001-model-image-compare/spec.md`

## Summary

使用 Python 单进程本地服务承载同源页面，HTTPX 共用请求层配服务商参数校验，SQLite 与文件目录保留轮次、图片、首次响应和重试。完成单图/多图独立检测、五模型比较、提示词微调、四项推理控制与历史对照。

设计结构已明确；真实模型接入仍受实际服务商和未确证参数上限限制。不将“完成正式计划”解释为五模型已可调用。

## Technical Context

**Language/Version**: Python >=3.12；原生 JavaScript、HTML、CSS。
**Primary Dependencies**: FastAPI、Uvicorn、HTTPX、Pydantic、Pillow、python-multipart；安装时通过 uv 锁定版本。本版不引入 LangChain。
**Storage**: sqlite3 标准库与本地 data/images；短事务，单数据库线程。
**Testing**: pytest、pytest-asyncio、HTTPX MockTransport，真实浏览器交互验证；真实推理需显式启用。
**Target Platform**: Windows 本地浏览器，服务仅监听 127.0.0.1:8000，单进程。
**Project Type**: 本地 Web 调试工具，现有 CLI 启动服务。
**Performance Goals**: 每模型最多1个在途请求、最多5路，逐项完成可见；活动轮次每秒刷新摘要；调用总期限180秒。
**Constraints**: 单活跃轮次，20图/轮、10 MiB/图、2000万像素；静态 JPEG/PNG/WebP；长边2048不放大，统一JPEG质量90。无生产服务运行依赖，不自动重试。
**Scale/Scope**: 单用户、五模型、工作台和历史两视图。图片组最多100个初始尝试。限值是本地设计默认值，不代表服务商极限。

## Constitution Check

宪章仍是占位模板，无可执行条款，不宣称通过已制定宪章。按本次用户指示、已确认 spec 与简单、局部修改原则评估：

- 研究前：范围、协议、首次响应留存、拒绝不兼容设置已确认，允许进行设计。
- 设计后：使用已有 Python 布局，标准库存储，无外部基础设施；密钥不进入浏览器或快照；测试不默认触发付费请求，符合现有约束。
- 接入门槛：能力未知时不可运行对应设置，页面不伪称等价；具体提供方补证是启用真实模型的前置条件，不阻止本地 fake 验收。
- 当前没有制定或修改宪章；无前后扩展钩子。setup-plan 返回的功能逻辑标识为001-model-image-compare，实际 Git 分支仍为master。

## Project Structure

### Documentation (this feature)

- [research.md](research.md)：决策、依据及接入门槛。
- [model-compatibility.md](model-compatibility.md)：官方证据矩阵。
- [data-model.md](data-model.md)：数据约束与状态。
- [contracts/http-api.md](contracts/http-api.md)：请求、响应、错误语义。
- [quickstart.md](quickstart.md)：实现后的验证指南，当前未执行。
- [technical-design.md](technical-design.md)：设计背景。契约细节以本计划关联文档为准。
- tasks.md 将在任务拆分阶段生成，本次不创建。

### Source Code (repository root)

以下为拟建布局，不代表已实现：

```text
src/hos_vlm_lab/
  __init__.py             # 现有CLI入口
  app.py                  # 路由与生命周期
  config.py               # 环境变量和能力配置
  models.py               # 请求/响应验证
  gateway.py              # HTTPX调用与提供方参数映射
  images.py               # 解码/预处理/文件留存
  store.py                # SQLite短事务
  runner.py               # 有界执行、停止与重试
  default-prompt.json     # 本地历史契约预置及来源
  static/index.html
  static/app.js
  static/styles.css
tests/
  test_contracts.py
  test_gateway.py
  test_images.py
  test_store.py
  test_runner.py
  test_api.py
  fakes.py                 # 共用测试替身
  browser_app.py           # 测试专用浏览器实例
  __init__.py
```

**Structure Decision**: 一个包、职责文件内直接函数/必要状态对象，无多级Provider或仓储继承体系。页面使用语义化控件、键盘可访问操作和文本方式渲染模型原文。

## Delivery and Validation

1. 配置、能力和协议 → 捕获请求证明严格字段映射、拒绝未知配置，原始文本不改写。
2. 图片与持久化 → 哈希一致、事务失败不调用、历史重启可读。
3. 调度与接口 → fake响应测试逐项完成、超时、停止竞争、请求去重与首次响应留存。
4. 页面 → 浏览器验收图片选择、字段提示、运行/停止、单项重试与两轮对照。
5. 真实接入 → 端点确认及缺失上限补证后，显式单图试运行，再按spec的三图五模型验收。

设计门槛：任何未知参数能力返回配置问题，不能以运行一次未报错证明参数有效。预算与temperature缺省宽松比较不进入第一版，严格遵循已确认参数合同。

