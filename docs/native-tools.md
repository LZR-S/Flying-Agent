# 原生工具协议

v1 使用原生工具调用：Gemini/Qwen 通过 Chat Completions 的 `tools`、`assistant.tool_calls` 和 `role=tool`；Astra 通过 Responses API，再映射到同一个内部工具循环。不把普通文本 JSON 或 Markdown 代码块解析为可执行指令。

## 请求与结果

```text
system: 摄影职责、工具交互约定、结束条件
user: 原始任务
assistant: tool_calls[{id, type: function, function: {name, arguments}}]
tool: tool_call_id + JSON 文本结果
... 已完成的工具交互历史 ...
user: 当前公共观察、预算、图片目录、当前/历史图片
```

首轮没有 assistant/tool 历史。工具定义放在请求顶层 `tools`，不再重复写入系统提示。所有模型使用 `parallel_tool_calls=false`。Gemini 使用 `temperature=0`、`tool_choice=auto`，不额外指定推理参数；Qwen 3.8 Flash 使用 `temperature=0`、`tool_choice=required` 并显式发送 `enable_thinking=false`。这两个 Chat Completions 分支不指定 `response_format` 或 `strict`。参数范围仍由本地 Pydantic 严格校验。发送前将本地 `$defs/$ref` 展开为内联对象，让嵌套复核字段在兼容 API 的工具 schema 中直接可见。

`gpt-6-astra` 经 OpenLux `/v1/responses` 使用 `reasoning={effort:medium}`、`tool_choice=auto`，不发送 `temperature` 或 `enable_thinking`。实测该服务拒绝 Chat Completions 的工具调用与 medium 推理组合，并拒绝工具 schema 顶层的 `oneOf`。Responses 适配仅从 act 的线上 schema 移除此顶层约束，保留字段和动作范围说明；本地 Action 校验仍严格执行原来的类型、每种动作范围和必填规则。Responses 工具显式 `strict=false`，保留可省略参数。

Responses 每轮从 ContextBuilder 选出的消息重建 `input`，以 `function_call_output` 回传文本结果，并以 `input_image` 发送同一组 JPEG。使用 `store=false`，不使用 `previous_response_id` 或服务端会话串联，避免旧图片绕过历史消融。保留服务返回的函数调用、消息及 reasoning 项（请求 `reasoning.encrypted_content`），只随已接纳的调用历史回传；重复调用 ID 不能重写已记录历史。请求/回复保存原生格式，离线审计覆盖 Responses 输入；统计将 input/output tokens 映射到共同报告字段，原始 usage 保留在回复文件中。请求 medium 不保证第三方报告非零 reasoning_tokens。

八个工具为 `act`、`capture`、`photo_frame`、`crop_photo`、`generate_reference`、`review_photo`、`view_images`、`finish`。每个工具的参数直接包含业务字段，以及：

- `based_on_frame_id`：本轮模型实际可见的导航帧 ID，不能被执行前的新帧替换。
- `note`：最多 800 字符的操作说明。

例如，`act` 的原生函数参数为：

```json
{
  "kind": "forward",
  "value": 40,
  "based_on_frame_id": "frame_000042",
  "note": "向前调整后重新观察"
}
```

`value` 仍为 Tello SDK 的整数厘米；原生协议不改变动作语义。

## 图像与历史

每次模型决策前，`AgentLoop` 自动调用内部 `Runtime.observe()`，推进运行层、检查传感流新鲜度，再构建当前完整 RGB 取景器、帧 ID/图像年龄、连接/飞行状态、电量和预算。工具被拒绝、协议错误和照片待复核时仍执行这条路径。模型不再调用 `observe`；内部采图和健康检查保留。自动观察不消耗飞行动作预算，画面也不保证与上一轮不同。确实需要等待时间经过时可用 `act(kind=hold, value=秒数)`，它沿用动作计数和复核限制；不能用来绕过待复核状态。

`tool.content` 仅包含 JSON 文本。下一条 `user` 消息携带图像字节，并通过 `message_kind=runtime_observation` 明确其传感器数据身份。`after_tool_call_id` 标识前一次工具交互；真实图片标签包含 `image_id`、原始曝光时间和已知的 `source_tool_call_id`；合成参考图只有生成时间 `created_at`，不伪造曝光时间。推理期间新产生的当前帧不冒充某次工具的返回帧，来源可以为空。

System prompt 说明自动输入、能力边界、摄影目标、视觉历史和“先复核、再决定调整或降落、最后交付”的生命周期；参数结构和范围放在顶层工具定义，实时状态只放在每轮最后的观察消息。历史交互保持原生 assistant/tool 文本。关闭导航历史时，提示明确禁止回看旧导航图，同时保留已拍照片的比较能力。

模型输入统一使用 JPEG quality 95，以 `data:image/jpeg;base64,...` 内嵌发送；当前取景器、历史导航帧及回看的原图/裁剪图都经过同一编码路径。不缩放、不交换颜色通道，每次直接从通过哈希校验的 PNG 生成 JPEG，避免重复有损压缩。磁盘中的导航证据、原始照片、预览和裁剪交付物仍保留 PNG。

`api/*.request.json` 保存实际发送的 JPEG 字节，离线输入审计计算这些字节的哈希。图片标签的 ID 对应 `images.json` 中的源 PNG；当前图标签额外带 `viewfinder`，绑定标注 PNG、原始帧 ID/哈希、曝光、画幅版本、矩形和辅助线。输入审计同时检查原始与标注 PNG 哈希、元信息及实际 JPEG 是否由该标注生成；复核中的 `image_sha256` 和 `source_sha256` 继续绑定源文件。模型复核基于 JPEG 副本，细节可能受有损压缩影响，不能将模型看到的字节与交付 PNG 的字节视为相同。

默认提供当前完整 RGB 上绘制虚线画幅和框内辅助线的取景器，以及前一轮、前两轮各自的最终完整导航帧。当前取景器只占一个图像槽位，不再额外发送实时裁剪预览；历史导航图保持无标注。一次模型回复及其工具处理构成一轮；普通工具拒绝和协议错误也登记轮末帧，不将入档顺序当作轮次。轮末读取已有相机流，不额外推进 tick；结果未知或执行中断时不合成轮末帧。历史不足两轮时按实际数量发送，相同帧 ID 不补发。每轮结果中的 `round_end` 保留轮次、帧 ID、曝光时间和已知调用 ID，图像标签的 `round_ends` 标明其关联轮次。`based_on_frame_id` 仍绑定模型实际看过的输入，不能改写成后来生成的轮末帧。

回看时提供当前图像及至多三张指定图片；若有待复核图或活跃参考图，其固定槽位优先，未呈现的请求 ID 在 `omitted_requested_image_ids` 说明。拍摄或裁剪后的下一轮自动提供当前图像、新候选图及至多两张已有候选图；裁剪时优先配对其原始照片，其余位置按创建顺序选最近候选。显式回看或拍后比较暂时替换自动导航历史，不为填满四张图而补入无关历史；下一次普通请求恢复轮末窗口。更早的导航帧 ID 保留在完整工具文字历史中，可用 `view_images` 请求。

历史 assistant/tool 消息只保留文本和服务商必要的签名/推理续接项，不保留旧图片块。每轮最多四个图像块：先按 ID 去重，再按解码后完整 RGB 的尺寸和像素哈希分组，每组只编码发送一份 JPEG。主标签的 `aliases` 保留共享像素的其他 ID 的完整公开元信息；不同曝光的时间、导航/照片/预览用途和各自源 PNG 哈希绑定不合并。复核可引用实际呈现的照片别名，但只有导航 ID 能作为 `based_on_frame_id`。不对近似画面做相似度过滤。

关闭导航历史时，先过滤旧导航 ID，再分组；即使旧导航图与当前图或照片像素相同，也不作为别名重新引入。原始照片、裁剪图和合成参考图仍可回看；不会因参考图保留了来源 ID 而重新发送旧导航源图。离线输入审计同时检查主标签与别名。图片元信息明确区分原图、裁剪图、像素尺寸、原始曝光和裁剪生成时间。

`image_catalog` 仅列本轮可见导航图、全部候选照片及合成参考图；当前取景器通过导航图标签中的 `viewfinder` 说明。`photo_review_state` 提供每张候选的最新复核 ID、履行状态和下一步建议。完整目录、照片文件、哈希和原始工具结果仍保留在本地运行记录。

工具文字结果采用字段白名单：保留状态、拒绝原因、动作 ID、轮末帧、照片尺寸/来源/裁剪区域及必要错误反馈；复核只回传登记 ID、照片 ID、履行状态和下一步建议，详细 checks/rationale 已在原始 assistant 调用中。文件路径和内部证据哈希不反复加入会话。最新电量、连接/飞行状态和预算由当前运行观察提供。保留完整文字会话，不另外追加重复记忆摘要，也不自动截断服务商续接内容。

`context_built` 事件记录轮次、上下文构建时间、候选/发送/合并图像数量、遗漏 ID、JPEG 字节数及各部分文本字符数。`api-metrics.jsonl` 的 `context` 从最终实际请求统计固定消息、工具 schema、历史（含服务商续接项）、当前状态、图像标签大小和图像 data URL 长度；API 重试保留相同上下文计量。`api-metrics.csv` 合并上述大小和该轮构建时间，并保留服务商返回的输入/输出/缓存 token、API 耗时。字符数和 JPEG 字节数不冒充 token；未返回的 token 仍记为缺失。

## 摄影目标与裁剪

System prompt 包含摄影软目标：主体可读性、画面平衡、有意义的留白、背景分离、线条、光色与原生细节。用户明确要求优先；不引入固定人物占比、强制网格交点放置、强制优化次数或美学门控。半身范围按原始任务判断，不额外要求大腿中点、固定可见比例或像素阈值；主观改善建议写入 `quality_issues`。模型依据实际图片比较收益与损失，可以保留符合输出契约的较早照片。

2026-09-29 起，System prompt 回补 v0 美学规范中不依赖检测器的摄影知识：先确定观者首先看到什么；框内逐项检查头脚留白、地面面积与脚下余量的区别、视线/身体朝向空间、头颈肩手边缘与栏杆/杆件/地平线的切线（色彩对比不能证明分离）、真实地平线与结构线位置、光色与原生细节；居中、三分、黄金分割、对称、环境框架、引导线、对角线和前景层次均为可选手法。机位因果以倾向表述：水平相机上升使主体下移（脚下余量减、头顶余量增），头脚跨越光轴时前进通常同时压缩上下余量，左右平移改变视差和背景重叠，偏航无视差、不能解除遮挡；不得为制造前景或框架接近未知空间。照片比较须指出决定性可见收益与退步，指令动作、时间先后、主体变大或贴近网格本身不构成改善证据。v0 的八维必填评分、候选方案表单、0.65 置信门槛、检测器几何与追像素试验未回补。系统提示同时删除与工具说明重复的机制描述，`tests/test_system_prompt.py` 保护关键规则至少在提示或对应工具说明中保留一处。默认 `framing_policy=max_native` 将最大原生尺寸落实为代码约束；操作者可在启动前选择 `--framing-policy flexible`，模型工具不接受策略切换。

`crop_photo` 从本轮已经保存的原始 `shot_` 照片创建一个独立 PNG。以下缩图示例仅适用于 `flexible` 模式：

```json
{
  "source_id": "shot_000001",
  "left": 280,
  "top": 60,
  "width": 400,
  "height": 600,
  "degradation_reason": "已落地，裁去边缘干扰；接受低于480×720的原生细节",
  "based_on_frame_id": "frame_000042",
  "note": "尝试2:3竖幅，减少空地，并检查头脚和手持物是否完整"
}
```

坐标是原始图片中的整数像素，左上角从 0 开始，矩形为 `[left,left+width) × [top,top+height)`。公开返回新的 `crop_000001`、实际分辨率与比例、原图 ID、原始帧 ID、裁剪矩形、原始曝光时间及单独的生成时间；原图和裁剪哈希保留在本地证据记录。例中的 400×600 输出为严格 2:3，低于 960×720 原图可取得的最大 2:3 矩形 480×720。在 `max_native` 下，即使填写理由也返回 `maximum_native_frame_required`；在 `flexible` 下必须填写非空 `degradation_reason`。最大尺寸裁剪可省略理由；显式 null 或空白理由无效。

在严格模式中，首次成功的 `photo_frame set`、带默认画幅的拍摄或手动裁剪锁定 `frame_contract`（输出比例、宽、高），后续工具和 `finish` 均须遵守。首次上下文自动初始化默认 16:9 最大画幅，版本为 0，暂不锁定比例；模型可先选择用户明确要求的比例。保留默认画幅直接拍摄则锁定默认比例。显式 clear 且尚未建立契约时仍可保存与交付完整原图。任务比例由 VLM 理解并选择，框架不猜测用户语义；它保证已选契约不被绕过，并不能证明最初选择就符合原始任务。

裁剪不缩放、不补像素、不修改原图、不产生新曝光，也不影响飞行状态。越界矩形被拒绝，不会静默截断。禁止任意路径、导航帧及裁剪图作为源；修改裁剪方案时再次指定原始 `shot_`。不设置人体检测或美学合格门槛，模型负责依据图片判断构图及完整性。

裁剪在降落前后均可调用，但仍受任务时间和步数预算约束。默认最多 6 次手动裁剪（`Config.max_crops`），与默认 3 次原始拍摄独立计数。`finish.shot_id` 可以选择原始 `shot_` 或裁剪 `crop_`；需要有效复核记录及确认落地。日志、JSON 和 HTML 报告分别保留原图和裁剪图，并明确最终交付来源及尺寸。

服务商在 `tool_calls[].extra_content.google.thought_signature` 返回的签名随原始工具调用一起保留，不解释或重写。实际请求、回复、PNG 字节和事件记录继续留档；认证头不写入记录。

## 持续 frame 与拍摄复核

两部分都在同一个 `AgentLoop` 中执行。没有独立摄影阶段，也不根据人物大小或美学评分开放工具。每次拍摄或裁剪后有一个由代码强制的复核检查点；完成后恢复正常工具决策。

`photo_frame` 设置示例业务参数（同时需要常规 `based_on_frame_id` 和 `note`）：

```json
{"mode":"set","aspect_ratio":"2:3","guides":"thirds"}
```

首次上下文按 `Config.default_aspect_ratio`（默认 16:9）初始化居中最大画幅，辅助线取 `Config.default_guides`（默认 `thirds`），不锁定契约。VLM 根据用户任务选择比例，在精细构图前设置；harness 不通过关键词猜测任务。省略 `rectangle` 时，代码按当前源图尺寸计算该比例的最大整数像素矩形并居中：960×720 输入的 2:3 为 `left=240, top=0, width=480, height=720`，1:1 为 720×720，16:9 为 960×540。比例使用正整数 `W:H`，约分后精确匹配；不能在源图内形成该比例的整数像素矩形时拒绝。画幅保持固定，模型依据实时预览自主调整机位，没有强制移动次数、距离或摄影阶段门控。

可显式提供同一比例、最大尺寸的 `rectangle` 调整框位置。`max_native` 禁止缩框；改变已经锁定的比例或尺寸返回 `frame_contract_locked`。只有 `flexible` 模式允许更小的矩形并要求非空 `degradation_reason`。任何拒绝均保持旧画幅与契约不变。

在 `flexible` 或尚未锁定契约时，使用 `{"mode":"clear"}` 关闭画幅，完全省略 `aspect_ratio`、`rectangle`、`degradation_reason`、`guides`。`max_native` 已锁定契约后不允许 clear。`set` 必须提供比例；可省略字段不接受显式 null，矩形必须是对象。线上 schema 不引入 nullable 联合类型或顶层 `oneOf`；模式与参数的条件关系由本地严格校验，错误反馈指出修正方式，不回显无效输入。

画幅状态、预览和成片的 `resolution` 包含源图尺寸、实际像素数、该比例的最大尺寸及像素数、`retained_source_fraction`、`retained_max_frame_fraction`、是否降级与理由。480×720 的 2:3 图保留源图 50% 像素、该比例最大画幅 100% 像素；280×420 则仅保留最大画幅约 34%。这些是分辨率指标，不代表主体细节或美学已达标。构图优先通过有益的机位调整完成，模型仍须考虑安全、可见性与预算。

`{"mode":"guides","guides":"golden"}` 只切换框内辅助线；支持 `none / thirds / golden`，该模式禁止比例、矩形和降级理由字段。`set` 可同时指定辅助线，省略则沿用当前设置。画框边界为单像素半透明白色虚线，框内辅助线更淡，线周围仅作轻微柔化。最大画幅只画原图内部的裁切边：竖幅左右两条、横幅上下两条；与原图重合的边界不重复描画。关闭辅助线仍保留内部裁切边界；未启用画幅时切换辅助线返回 `photo_frame_required`。

每次显式成功设置、关闭或切换辅助线递增版本；越界或非法参数不改变已有设置。frame 固定在传感器像素坐标，不跟踪人物，不控制云台或无人机。完整 RGB 始终保留用于导航，实时预览由同次曝光生成，记录 `source_frame_id` 和 `frame_version`。预览不会登记为拍摄照片，也不能被回看、复核、交付或用作导航 `based_on_frame_id`。原有 `set_photo_frame`、`clear_photo_frame` 和 `observe` 不再注册，也不保留执行别名；旧脚本需更新工具调用，历史运行证据保持原样。

图像优先级为当前完整取景器 → 待复核成片（若有）→ 活跃参考图 → 显式回看或拍后比较（裁剪优先原图）→ 前两轮最终导航帧。当前取景器始终固定，只占一个槽位；清洁的实时裁剪预览只供工作台查看，不占模型输入槽位。显式回看或拍后比较时暂停自动导航历史。上限按四个不同像素的图像块计算，别名不额外占槽；标注取景器与无标注照片像素不同，不会错误合并。待复核成片始终保留自身 ID，超出剩余槽位的显式请求列入 `omitted_requested_image_ids`，模型可分轮查看。

模型收到的当前图保留原始导航 `frame_` ID，`based_on_frame_id` 引用该 ID；`viewfinder_` 只标识标注证据，不可回看、复核、交付或用于导航。`context_built.viewfinder_id` 记录该轮实际标注版本，避免同一曝光切换辅助线后回放错图。框外像素不被遮蔽、变暗或改写；虚线与辅助线仅是显示标注，不代表场景物体或深度。

有待改善反馈、已有运动指令且没有显式回看时，构图上下文将最近运动所依据的导航图排在活跃参考图之前，支持观察前后变化；当前取景器仍优先。导航历史关闭时，不提供这张旧导航图。该图是模型作决策时见到的曝光，不冒充执行前一刻的传感帧。

启用 frame 后，`capture` 先保存完整 `shot_` PNG，再从该实际拍摄曝光生成 `crop_`，记录 `derivation=photo_frame`、原图 ID/哈希、曝光时间和 frame 版本；不使用上轮预览充当拍摄，原图与成片均不含虚线或辅助线。原图及 frame 成片分别需要复核；严格模式中，若原图比例/尺寸与契约不同则不能选为交付，`finish` 返回 `delivery_frame_mismatch`。自动 frame 成片每次曝光最多一张，计入 `max_photos` 对应的拍摄操作，不占手动裁剪预算；`crop_photo` 仍受 `max_crops` 约束。无缩放、补边或静默截断。

`review_photo` 示例业务参数：

```json
{
  "image_id":"crop_000001",
  "checks":[
    {"requirement":"严格2:3竖幅","status":"satisfied","evidence":"保存尺寸480×720，比例为2:3。"},
    {"requirement":"全身完整","status":"unknown","evidence":"脚部被前景遮挡，无法确认完整性。"}
  ],
  "quality_issues":["脚部遮挡；背景线条靠近头部。"],
  "next_step":"finish",
  "rationale":"保留当前最佳候选并明确未满足项，结束任务。"
}
```

代码校验图片确实出现在本次请求中、结构字段有效、图像和原图哈希未变，然后追加 `agent-photo-reviews.json`。不可见图片返回 `review_image_not_visible` 并排入下一轮；`finish` 遇到未复核的选片返回 `review_required`，遇到仍选择继续的复核返回 `review_not_final`，同样展示实际图片供下一轮复核。新裁剪不继承原图复核；相同成片的有效复核不会因导航帧变化或降落失效。

`checks.status` 为 `satisfied / unsatisfied / unknown`，逐项附证据；`quality_issues` 可以为空，`next_step` 为 `continue / finish`，必须附非空 `rationale`。全部检查 satisfied 的交付标记 `completed`；任一 unsatisfied 或 unknown 标记 `partial`，无需无限重试。无待复核成片时，放弃允许落地后直接 `finish(shot_id=null, abandon=true)`。

每次成功 `capture / crop_photo` 后，`AgentLoop` 设置 `pending_review_id`：无 frame 时指向原图，启用 frame 时指向自动生成的 framed crop。原图作为曝光证据保留；以后若改选原图，仍须单独复核。待复核状态下，允许 `review_photo` 复核该指定图片、`view_images` 比较，以及 `act stop` 停止移动；当前观察仍自动更新。其余调用返回可恢复的 `photo_review_pending`，不会下发动作、消耗动作预算或创建额外照片。包括 `hold`、普通 `land` 和 `photo_frame` 三种模式在内的操作必须等待复核完成。

只有对指定成片的有效复核能清除检查点。复核旧图、格式错误和查看其他图片均不会清除它；候选图片会继续出现在下一轮输入中。`next_step=continue` 同样清除检查点，让模型自行选择机位调整、重拍或其他操作；代码不代替模型执行计划，也不强制达到审美评分。

复核中存在 unsatisfied/unknown，或 next_step=continue 时，最新检查项、质量问题和说明写入 `composition_feedback`，每轮持续提供，动作不会清空它。一次有效的 satisfied/finish 复核才清除反馈。这里保留的是模型检查结果，不是额外的人体检测或独立真值；目前也不自动验证检查项是否覆盖全部任务要求。

已完成的平移、旋转和起飞增加 `motion_sequence` 并记录动作 ID、请求量、依据帧与说明；拒绝/未知动作不增加序号，降落也不作为构图改善。导航曝光首次留档时记录序号，拍摄继承曝光序号，裁剪继承原照片序号。它只表示指令顺序，不表示实际位姿或位移。`motion_context` 每轮显示最近运动和之后保存的曝光，提示当前调整是否尚未拍摄。

`max_native` 中，对运动前已判不合格/未知的曝光进行事后裁剪，或试图将其重新复核为 satisfied，返回 `fresh_capture_required`；新的机位成果必须由新曝光支持。原先已判合格的旧照片仍可选用，以支持尝试优化后选回较好结果；旧照片也可保留 unsatisfied/unknown 评价并作为部分交付，或放弃任务。重新保存相同帧不会重置其曝光序号。这些限制不阻止安全降落或异常收尾，也不要求固定移动次数。

正常路径为 `capture → review_photo → 调整/重拍或land → finish`；新的裁剪也会触发新的检查点。系统低电量、取消、越界、超时、API 错误、步数或其他预算耗尽仍由运行层直接收尾降落，不等待复核。未完成的 `pending_review_id` 保留在运行总结；`review_checkpoint` 事件记录所需/完成状态和当时是否在空中，HTML 中可回放。此前允许 `capture → land → review_photo` 的行为已收紧，历史测试报告保留原始行为。

这些约束保证模型提交了可追溯的复核，并不证明其检查覆盖了所有要求、证据属实或美学判断正确。照片任务的独立验收继续使用 `photo-review.json`；HTML 和 JSON 分开呈现 agent 自评与独立评测，未盲审项目保持待评。固定飞行检查脚本没有视觉判断能力，因此提交 unknown 复核并交付为 partial，不自动假设摄影成功。

## 调度与错误

每轮一个工具调用是当前执行器的约束，不是原生 API 的限制。飞行动作串行执行，模型在获得新图像后决定下一步。原生协议迁移没有增加动作批处理或并行执行。

- 同轮多个调用：整轮拒绝，不执行任何调用；给每个有效调用 ID 配对返回错误。
- 参数越界、未知工具、未见过的帧引用：拒绝调用，下一轮允许纠正。结构错误附 `validation_errors`，包含字段路径与错误类型；类型错误还附期望类型、实际 JSON 类型和简短说明，`rectangle` 类型错误提供固定结构示例。反馈不复制内部异常上下文或原始输入，不自动解析嵌套 JSON 字符串。
- 无法重放的消息、非法 JSON、函数名不符合 `[A-Za-z0-9_-]{1,64}`、同轮重复 ID 或复用历史 ID：保存原始回复，向下一轮提供文本协议错误，不把非法消息加入原生交互历史。
- 连续三次协议错误：终止并执行既有收尾流程。
- 动作 ID 使用 `native:{tool_call_id}`；HTTP 重试仅发生在推理请求阶段，不能重新派发已开始的动作。

Webots 起飞独立确认：水平偏差不超过 15 cm、垂直误差不超过 10 cm、速度不超过 5 cm/s，连续满足 0.5 秒。平移仍要求水平和垂直目标误差均不超过 3 cm、速度不超过 3 cm/s，连续满足 0.5 秒；漂移重置稳定计时，超时优先。水平位置环加入有界积分补偿，只在离地、接近目标且低速时累计，避免地面和大幅移动期间累积误差；起飞初始化和电机停止清空补偿。内部传感量不进入模型输入，Tello 真机 ACK 语义保持不变。Webots 脚本验证的范围与结果见实现记录。

## 验证依据

2026-09-22 的兼容性探针位于 `runs/api-native-tools-20260922/`。同一 API 上，直接在 `tool.content` 中嵌入图片的一次探针未得到预期语义结果；文本工具结果加 `user` 图片的探针通过。因此采用后者。HTTP 接受某字段不等于服务端严格执行其语义，此结果也不证明所有服务商都无法处理工具图片。

生产组件的接线测试位于 `runs/native-tools-integration-20260922/`：`CloudPolicy + ContextBuilder + AgentLoop + Runtime` 使用已落地的模拟相机执行拍照、回看、选片。结果以该目录中的 `results.json` 为准。此测试不启动 Webots，也不验证实际飞行能力。

本次接线结果：`gemini-3.6-flash` 连续完成 `capture → view_images → finish`，3 次请求均 HTTP 200，无重试，总耗时 66.13 秒。每轮分别发送 1、2、2 张图片；图中文字识别、工具 ID 配对、原始调用及签名回传、公共字段审计全部通过。模拟后端始终处于已落地状态，动作请求为 0。

新增 frame/复核验证位于 `runs/frame-review-inline-integration-20260922/`：4 次 API 调用、60.24 秒，依次完成 `set_photo_frame → capture → review_photo → finish`，交付 320×480 的 2:3 成片。原始字节、裁剪像素、曝光关联和复核哈希均通过核对；无飞行动作。本地 136 项测试通过。首次使用嵌套 `$ref` 的接线运行保存在 `runs/frame-review-integration-20260922/`，复核参数校验未通过并由操作方终止；后续展开 schema 并增加字段错误反馈后，上述独立重测通过。历史运行记录保持原样。


## 可选参考图与实拍闭环

`generate_reference` 的业务参数示例（另带共同的 `based_on_frame_id` 和 `note`）：

```json
{
  "source_id": "frame_000042",
  "guidance": "保持现场人物、服装和环境，尝试头顶至大腿的自然平衡构图",
  "aspect_ratio": "2:3"
}
```

来源必须是当前请求实际可见、哈希未变的真实导航 `frame_` 或完整拍摄 `shot_`。裁剪、预览、合成参考和任意路径均不接受。`aspect_ratio` 支持 2:3 / 4:3，分别请求 1024×1536 / 1024×768；实际生成尺寸单独记录，不假定服务端遵循请求。原始用户任务始终直接传入生成提示，guidance 不能代替它。生成提示强调保持人物身份、姿态、衣物、场景、光照和渲染风格，并限定固定相机、飞行动作与裁剪的能力；不发送内部位姿、净空、检测器或评测数据，不另起分析/评分 VLM 工作流。

独立客户端向 `/v1/images/edits` 发送源 PNG multipart（image）及 `model=gpt-image-2, n=1, quality=medium, size, output_format=png, prompt`。只接受单张内嵌 base64 PNG，不下载返回的远程 URL。限制响应体与解码尺寸。凭据走独立环境变量，不能误用选中的阿里云决策接口。

接入点在统一 AgentLoop 中：可选生成 → 自主调整真实机位/取景框 → capture → 强制实拍复核 → 自主决定继续优化或降落交付。生成不是拍摄门槛，也不引入固定移动策略。`Config.max_references=1`、`reference_timeout_s=70`；预算包括失败尝试，参数拒绝与未配置服务不计网络尝试。可将上限设为 0 关闭。无自动重试。生成线程只返回数据，主控制线程逐 tick 服务飞控、健康检查和预算；只有有效 epoch 和期限内的结果能注册/激活参考。取消、低电量、图像过期、任务到期照常收尾；迟到回复至多保留服务端证据，不能改变任务状态或重新取得飞行执行权。

生成成功后登记 `ref_000001`：`kind=reference, synthetic=true`，记录源图 ID/哈希、生成时间、模型、参数、usage、实际尺寸与自身哈希；不增加拍照/裁剪/飞行动作计数。首次展示优先配对真实源图（关闭导航历史时不发送旧导航源图）。后续请求优先顺序为当前真实 RGB 取景器 → 待复核候选 → 活跃参考 → 指定回看 → 默认轮末历史，总计仍不超过四个唯一图像块。参考图占用槽位，可能挤掉部分历史。生图实际上传原始无标注 PNG，不将取景框或辅助线作为场景内容。

有活跃参考时，实拍 `review_photo` 必须额外包含：

```json
{
  "reference_comparison": {
    "reference_id": "ref_000001",
    "use_reference": false,
    "reason": "合成图改变了人物姿态，无法直接作为目标",
    "differences": ["实拍保留了真实手持物；参考图遗漏了该物体"]
  }
}
```

照片与参考都必须在本次输入实际可见，代码校验双方和来源哈希。`use_reference=false` 停止自动附带参考，不删除图像；仍可回看，并在新的实拍复核中明确重新采用。相似度不是合规判据，checks 始终针对原始任务和真实交付像素。生成新参考后不能复用未比较该参考的旧复核直接交付。待拍后复核时，生图也被阻止；必须先复核已拍照片。

工作台和 HTML 报告将合成参考与候选照片分区展示。`reference-api/` 保存实际生成参数/提示、源 PNG 与哈希、白名单响应（图片和 token usage），不保存认证头及任意服务商文本；`reference-metrics/` 记录每次工具等待时间、状态、终止原因、usage，与决策 API 统计分开。`trace.jsonl` 包含 reference_started / reference / reference_attempt 和结构化实拍比较。离线审计覆盖生成请求字段和源图字节。未提供的 usage 保留为 null；超时/取消后尚未收到的服务端 usage 不计入已完成统计。
