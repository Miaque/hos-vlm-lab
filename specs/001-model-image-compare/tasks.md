# Tasks: 多模型图片对比调试

**Input**: [spec.md](spec.md)、[plan.md](plan.md)、[research.md](research.md)、[data-model.md](data-model.md)、[接口契约](contracts/http-api.md)、[quickstart.md](quickstart.md)。
**Prerequisites**: 设计完成；实际端点及部分参数上限尚待取证，真实调用任务不得以模拟结果关闭。
**Tests**: 按规格验收场景与计划执行针对性验证；相关测试先复现失败再实现，不引入与本功能无关的测试。
**Organization**: 按用户故事组织；本地实现及模拟验收已完成，真实取证与调用验收待完成。路径相对仓库根目录。[P]仅表示同阶段明确前置完成后可以并行，不授权自动创建代理。未请求时不提交或推送。

## 当前进度（2026-09-11）

- 已完成 **33/35**：T001–T029、T031、T032、T034、T035，包含本地实现、自动测试、模拟浏览器验收及文档收尾。
- 未完成 **2/35**：T030（实际提供方/地域/端点与参数范围取证）、T033（真实单图及三图五模型验收）。
- 本次复核：`uv run pytest -q` 为 **66 passed，2 个依赖弃用警告**；`uv build` 成功。
- 验收细节、浏览器记录与未验证边界见 [validation.md](validation.md)。33/35 是任务完成度，不代表四款真实模型接通率。

## Phase 1: Setup

- [x] T001 在 pyproject.toml 和 uv.lock 添加并锁定计划中的运行依赖与pytest/pytest-asyncio开发依赖，保持现有src布局；验证uv同步与包导入。
- [x] T002 [P] 在 .gitignore 和 .env.example 定义data与密钥忽略规则、四模型连接前缀及无真实凭据示例，明确未配置模型不可用。
- [x] T003 [P] 在 tests/fakes.py 定义可复用fake网关和能力，在 tests/conftest.py 建立临时数据目录与显式测试配置夹具，默认不加载真实密钥、不发起真实网络调用。

## Phase 2: Foundational

目标：共用契约、存储与资源生命周期就绪；严格参数预检放在基础阶段，避免US1先实现一个不安全的调用入口。

- [x] T004 在 tests/test_contracts.py 先覆盖JSON提示词事件身份、严格events响应、数值/布尔混淆、空白证据、非法编码与统一错误结构，再在 src/hos_vlm_lab/models.py 实现对应契约。
- [x] T005 在 tests/test_gateway.py 覆盖提供方未知、温度固定/无效、预算关闭省略、上限未知拒绝等情况，再在 src/hos_vlm_lab/config.py 实现环境配置和有证据的能力校验；未知上限不填推测值，fake能力只由测试注入。
- [x] T006 在 tests/test_store.py 覆盖原子创建、request_id同内容复用/异内容冲突及外键约束，再在 src/hos_vlm_lab/store.py 建立images/rounds/round_images/attempts表与单线程短事务访问；凭据不得进入快照。
- [x] T007 在 src/hos_vlm_lab/app.py 和 src/hos_vlm_lab/__init__.py 实现单进程127.0.0.1入口、lifespan共享HTTPX与存储资源、同源写入约束和统一错误处理；在 tests/test_api.py 验证Host/Origin限制、资源关闭与无密钥回显。

Checkpoint：测试契约与本地资源生命周期可运行；真实提供方能力不完整不妨碍测试夹具验证。

## Phase 3: US1 同图多模型检测对比 (P1，MVP)

目标：两图两模型得到四个独立结果，逐项可见；有效空结果与错误可区分。
独立验收：使用受控模型响应完成规格US1五个场景，真实模式仅启用已取证配置。

- [x] T008 [P] [US1] 在 tests/test_images.py 覆盖静态格式、动画拒绝、10MiB/2000万像素/20图边界、EXIF、透明背景、哈希与整批失败，然后在 src/hos_vlm_lab/images.py 实现2048长边不放大/JPEG90预处理、原子文件写入与原图留存。
- [x] T009 [P] [US1] 在 src/hos_vlm_lab/default-prompt.json 整理hos-analysis初筛指令与历史事件种子，记录来源日期及版本，不依赖生产目录在线；在 tests/test_default_prompt.py 验证事件身份完整、编码唯一及输出协议一致。
- [x] T010 [US1] 在 tests/test_gateway.py 捕获同图同文请求、首次HTTP/模型原文、超时/429/截断错误和零自动重试，再在 src/hos_vlm_lab/gateway.py 实现HTTPX共用调用与提供方字段映射，保存实际参数及原始usage。
- [x] T011 [US1] 在 tests/test_runner.py 验证图片×模型组合、每模型单在途、最多4路、慢模型隔离、事务失败不调用，然后在 src/hos_vlm_lab/runner.py 实现单活跃轮次与逐项结果持久化。
- [x] T012 [US1] 在 src/hos_vlm_lab/app.py 实现GET /api/config、POST /api/images、图片读取、POST /api/rounds、轮次与尝试详情；在 tests/test_api.py 验证202接纳、422/413/404/409、上传整批失败与请求去重；创建轮次独立校验1–20图，覆盖0/1/20/21及分批上传后合并21图，拒绝时零记录零调用。
- [x] T013 [US1] 在 src/hos_vlm_lab/static/index.html、src/hos_vlm_lab/static/app.js、src/hos_vlm_lab/static/styles.css 实现图片组预览、模型勾选、初始合法设置运行和逐模型结果卡片，活动期每秒刷新、原文按文本展开、终态停止轮询。
- [x] T014 [US1] 在 tests/__init__.py 与 tests/browser_app.py 提供仅测试用启动入口，复用 tests/fakes.py 注入app工厂、独立数据目录、明确模拟标识并拒绝出站网络；依赖T007/T013就绪后按 specs/001-model-image-compare/quickstart.md 用真实浏览器连接该实例验证两图两模型、渐进结果、空events与失败区分，将操作证据写入 specs/001-model-image-compare/validation.md，明确为模拟模型结果。

Checkpoint：US1最小闭环可用；不以fake成功宣称四真实模型已接通。

## Phase 4: US2 编辑提示词和四项控制 (P1)

目标：用户可修改全部输入，预检拒绝不兼容设置，实际输入可追溯。
独立验收：准备有效/无效能力配置，验证US2四个场景和SC-002；复用US1调用闭环。

- [x] T015 [P] [US2] 在 tests/test_controls.py 编写思考开关、budget空/零/正数、temperature边界、输出与预算组合、某模型不兼容时整轮不调用的测试，使用明确假能力及实际映射样本。
- [x] T016 [P] [US2] 在 tests/test_prompt_snapshot.py 编写完整文本逐字保留、允许集合来自当前JSON、运行中编辑不影响快照及恢复默认不改历史的测试。
- [x] T017 [US2] 在 src/hos_vlm_lab/config.py、src/hos_vlm_lab/models.py、src/hos_vlm_lab/gateway.py 和 src/hos_vlm_lab/app.py 完成严格四控制的执行前校验与实际参数快照输出，使T015/T016通过；不增加“不指定/各家默认”放宽。
- [x] T018 [US2] 在 src/hos_vlm_lab/static/index.html 和 src/hos_vlm_lab/static/app.js 完成完整JSON提示词编辑、恢复默认、四项控制、预算禁用与逐模型错误提示，原始参数可查看；运行中编辑只用于下一轮。
- [x] T019 [US2] 在 specs/001-model-image-compare/validation.md 记录浏览器有效/无效参数、恢复默认和未隐式改写的验收结果，验证密钥不出现在配置响应或快照中。

## Phase 5: US3 微调与历史对照 (P2)

目标：同图不同提示词创建独立轮次，重启后历史图片和结果仍可查看。
独立验收：使用两轮预置记录与原上传文件移动场景验证US3及SC-004。

- [x] T020 [US3] 在 tests/test_history.py 覆盖两轮快照不可覆盖、分页、源文件移走后图片可读、重启中断状态及无自动调用；在 src/hos_vlm_lab/store.py 完成历史查询和queued/running中断恢复。
- [x] T021 [US3] 在 src/hos_vlm_lab/app.py 实现GET /api/rounds分页和跨轮快照查询，启动恢复中断、浏览器刷新可找到活动轮次；在 tests/test_api.py 覆盖边界分页与缺失记录。
- [x] T022 [US3] 在 src/hos_vlm_lab/static/index.html、src/hos_vlm_lab/static/app.js 和 src/hos_vlm_lab/static/styles.css 实现图片组复用、新轮次及两轮对照，按身份/哈希对应图片、缺模型显示未运行、预处理差异明确标记。
- [x] T023 [US3] 按 specs/001-model-image-compare/quickstart.md 执行两轮对照、源文件移动与程序重启浏览器验收，写入 specs/001-model-image-compare/validation.md，确认历史原文、参数及图片完整。

## Phase 6: US4 停止、重试与费用 (P2)

目标：停止未开始项、单项重试不覆盖首轮，并正确展示实际用量和估算费用。
独立验收：用成功/失败/待开始混合场景、用量与价格固定样本验证SC-005/006。

- [x] T024 [P] [US4] 在 tests/test_stop_retry.py 先覆盖停止/认领竞争、幂等停止、单项重试去重、配置身份变化拒绝、旧stop标志不吞重试和重试也受并发限制；覆盖历史停止后重试的running→终态、重试再次停止的stopping→终态、无活动批次停止不改变历史。
- [x] T025 [P] [US4] 在 tests/test_usage_cost.py 先覆盖未知用量、零值、reasoning包含于output不重复计费、缓存与时段缺失、Decimal复算及失败调用用量留存。
- [x] T026 [US4] 在 src/hos_vlm_lab/runner.py 和 src/hos_vlm_lab/store.py 实现独立批次cancel_requested及data-model.md的状态汇总优先级、停止同步边界、追加重试/关联ID、重启不自动恢复、数据库写失败后停止新调度，保证T024通过。
- [x] T027 [US4] 在 src/hos_vlm_lab/config.py 和 src/hos_vlm_lab/gateway.py 定义并文档化可选价格环境配置、保存价格快照、归一化usage和Decimal计费，保证T025通过；不同计价字段缺失显示未知，不用预算估算消耗。
- [x] T028 [US4] 在 src/hos_vlm_lab/app.py 和 tests/test_api.py 实现并验证停止/单项重试接口、不可重试409、同request_id不同目标冲突及尝试明细用量费用字段。
- [x] T029 [US4] 在 src/hos_vlm_lab/static/index.html 和 src/hos_vlm_lab/static/app.js 完成停止、失败项重试、独立尝试编号、耗时/token/费用及未知显示；在 specs/001-model-image-compare/validation.md 记录浏览器US4验收。

## Phase 7: Cross-Cutting & Release Validation

- [ ] T030 在 specs/001-model-image-compare/model-compatibility.md 补齐实际提供方/地域/端点与模型参数范围证据，并在 src/hos_vlm_lab/config.py 仅启用已确证profile；需用户端点信息时明确等待，不能因未报错便宣称参数生效。
- [x] T031 在 tests/test_api.py 和 tests/test_gateway.py 完成跨流程凭据脱敏、任意路径拒绝、模型原文不执行及无默认付费调用回归；执行全部聚焦测试与uv build，结果写入 specs/001-model-image-compare/validation.md。
- [x] T032 在 README.md、.env.example、AGENTS.md 和 specs/001-model-image-compare/quickstart.md 同步真实启动/测试命令、价格配置、限制和已实现结构，移除过时五模型/未实现描述，仅修改与交付有关内容。
- [ ] T033 在 specs/001-model-image-compare/validation.md 记录显式真实单图验收，再按SC-001执行三图五模型；依赖T030、合法配置及真实调用授权，无条件时保持未完成并说明已验证边界，不替换为fake通过。

## Dependencies & Execution Order

- Phase1：T001后可并行T002/T003；Phase2按T004→T005→T006→T007。
- US1：T008与T009独立；完成后T010→T011→T012→T013→T014。
- US2：依赖US1；T015/T016可并行，然后T017→T018→T019。
- US3：依赖US1及US2的输入编辑，T020→T021→T022→T023。
- US4：依赖US1基础运行和US3中断恢复；T024/T025可并行，然后T026→T027→T028→T029。
- 最终：T030接入取证可在任何阶段独立推进，但不可和config.py实现同时编辑；T031在四故事完成后执行，T032其后，T033依赖全部本地验证及T030。
- 图：Setup → Foundational → US1(MVP) → US2 → US3 → US4 → 本地交付；接入取证 → 真实验收。

## Parallel Examples

- US1：T008图片处理与T009默认材料为不同文件，可并行。
- US2：T015参数测试与T016文本快照测试为不同文件，可并行。
- US3：共享store/app/UI修改多，推荐顺序执行；无安全并行任务对，不强行拆分。
- US4：T024停止重试测试与T025计费测试可并行。

## Implementation Strategy

先完成基础和US1闭环，以明确模拟标识演示；再交付US2可调参数和提示词、US3历史、US4运行管理。每个故事验收后再推进依赖故事。同一文件的任务不得并行写入。勾选对应实现与验证证据见 [validation.md](validation.md)；真实验收不得以模拟验证替代。

实际提供方不明仅限制T030/T033及对应profile启用，不得成为不实现其他任务的理由。宪章仍是未填写模板，不能借模板示例创建额外审批或降低既有验收标准。

## Coverage

| 规格需求 | 实现任务 |
| --- | --- |
| FR-001 | T002,T005,T012,T030 |
| FR-002/003 | T008,T011,T012,T013 |
| FR-004 | T009,T016,T018 |
| FR-005/006 | T005,T015,T017,T018 |
| FR-007 | T006,T010,T016,T017 |
| FR-008/009 | T004,T010,T013,T014 |
| FR-010 | T011,T013,T020,T026 |
| FR-011/012 | T010,T024,T026,T028,T029 |
| FR-013 | T025,T027,T028,T029 |
| FR-014/015 | T020,T021,T022,T023,T026 |
| FR-016 | T009,T014,T032 |
| SC-001 | T011,T014（模拟）；T033（真实） |
| SC-002/003 | T004,T010,T015,T016,T019 |
| SC-004 | T020,T023 |
| SC-005/006 | T024,T025,T029 |


## 2026-09-11 新增模型

- [x] T034 新增 qwen3.6-27b 独立 BASE_URL/API_KEY 配置槽位，单轮上限扩为五模型；验证地址拼接、密钥隔离、未知能力拒绝及五路串行隔离，同步规格与配置说明。全套 64 passed，uv build 成功。
- T030/T033 纳入第五款的实际端点与能力取证、真实验收；仍未完成，三图五模型目标为 15 项。此前四模型模拟记录保留为历史证据。

- [x] T035 原四模型统一读取 VLM_BASE_URL/API_KEY，27B 保持独立连接；停止读取旧的逐模型连接配置，同步文档，验证共享连接、模型身份保留、缺失不回退及密钥隔离。全套 66 passed，uv build 成功。
