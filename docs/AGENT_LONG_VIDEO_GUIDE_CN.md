# MiniMax H3 时间线导演台：长视频生成 Agent 操作规范

> 本文面向负责策划、生成、检查和拼接长视频的视频生成 Agent。它不是普通用户界面介绍，而是一份执行规范。

## 1. Agent 的目标

使用 MiniMax H3 Ref2VA 和本插件，把长视频任务拆成多次 4–15 秒的短片生成，并通过相邻片段之间的固定重叠区保持：

- 人物身份、服装、姿态和站位连续；
- 场景、光照、天气与空间关系连续；
- 镜头运动、动作速度与剪辑节奏连续；
- 对白、环境声、音乐和音色连续。

最终成片不是简单首尾相接。除第一段以外，每个生成片段的开头都包含一段已经存在于上一段末尾的固定 Guide；合并时必须删除这段重复内容。

## 2. 开始前的强制要求

### 2.1 必须使用 MiniMax H3 官方提示词 Skill

每一段提示词都必须遵循 MiniMax H3 官方 `h3-prompt-writing` Skill：

- 官方仓库：<https://github.com/MiniMax-AI/MiniMax-H3>
- 安装命令：

  ```bash
  npx skills add https://github.com/MiniMax-AI/MiniMax-H3 --skill h3-prompt-writing
  ```

如果当前 Agent 环境不支持上述安装命令，必须从官方仓库读取以下文件，并把它们作为当前任务的提示词规范：

```text
.agents/skills/h3-prompt-writing/SKILL.md
.agents/skills/h3-prompt-writing/references/ref-en.txt
```

不得在没有阅读 Skill 和 `ref-en.txt` 的情况下，凭经验自由编造 H3 Ref2VA 提示词格式。

### 2.2 Ref2VA 提示词必须保持六段式结构

按以下顺序书写，字段名不可改名、不可换序：

```text
subject_definitions:
summary:
retention_analysis:
detailed_description:
overall_soundscape:
non_diegetic_music:
```

六个部分使用英文书写；对白、歌词和画面中可见文字保留原语言。每个镜头都应描述构图、人物位置、环境、动作、镜头运动、声音，以及参考素材实际生效的位置。

### 2.3 H3 的单次生成边界

根据 MiniMax H3 官方仓库当前规格：

- 单次输出时长：4–15 秒；
- 输出帧率：24 FPS；
- 参考图片：最多 9 张；
- 参考视频：最多 3 段，每段 2–15 秒，视频参考总时长不超过 15 秒；
- 参考音频：最多 3 段，每段 2–15 秒，音频参考总时长不超过 15 秒；
- 所有类型参考文件合计最多 12 个。

所以一分钟视频必须由 Agent 编排多次生成，不能把整分钟任务交给一次 H3 推理。

## 3. 核心概念：重叠生成

设每次生成文件的长度为 `G` 秒，相邻片段固定重叠长度为 `O` 秒：

```text
第1段贡献的新内容：G 秒
后续每段贡献的新内容：G - O 秒
N段合并后的长度：G + (N - 1) × (G - O)
```

例如每段生成 10 秒，并固定上一段最后 2 秒：

```text
Segment 1：生成 10 秒，累计 10 秒
Segment 2：前2秒重复 + 新增8秒，累计 18 秒
Segment 3：前2秒重复 + 新增8秒，累计 26 秒
……
```

一分钟的一个可行编排是：第一段 10 秒，随后六段各生成 10 秒，累计 58 秒；最后一段生成 4 秒，其中前 2 秒为重叠 Guide、后 2 秒为新内容，最终得到 60 秒。

推荐重叠范围为上一段最后一个镜头中稳定、可辨识的 1–2 秒。不要机械固定为 2 秒，应根据以下内容选择：

- 快速动作、运镜或对白跨段时，使用足以覆盖动作趋势和声音节奏的重叠；
- 静态镜头可以缩短，但应让人物位置、视线和环境关系清晰可见；
- 不要把重叠边界放在嘴型中间、快速闪切中间或动作最模糊的一帧；
- 重叠帧数以导演台显示的 `GUIDE N帧` 为最终依据。

## 4. 标准长视频生成流程

### 4.1 先建立全片规划

Agent 在首次生成前必须维护一份全局计划，至少包含：

| 字段 | 含义 |
| --- | --- |
| `global_shot_id` | 全片镜头编号，不随分段重新编号。 |
| `segment_id` | 本次 H3 生成批次。 |
| `target_duration` | 本段输出长度。 |
| `overlap_duration` | 与上一段重复的 Guide 长度；第一段为 0。 |
| `source_shot` | 本段开头继承自上一段的全局镜头。 |
| `new_shots` | 本段新增或继续发展的镜头。 |
| `visual_refs` | 本段实际需要的图片和视频素材。 |
| `audio_refs` | 本段实际需要的独立音频和视频原声。 |
| `splice_frame` | 合并时删除 Guide 后的首个保留帧。 |

全局镜头编号用于项目管理；H3 提示词中的 `[Shot 1]`、`[Shot 2]` 是每次生成内部的局部编号。Agent 必须维护两者的映射，不能混淆。

### 4.2 生成第一段

1. 根据作者要求上传本段需要的参考图片、视频和音频。
2. 调整素材顺序，并读取节点底部“提示词编号”。
3. 按官方 Skill 为第一段撰写完整六段式 Ref2VA 提示词。
4. 生成并检查人物、动作、构图、声音和最后一个镜头。
5. 如果结果不合格，不要把错误结果继续传递到后续片段。

### 4.3 为下一段建立固定重叠

1. 把上一段的生成结果上传到导演台视频轨道。
2. 用低清预览和红色播放头找到上一段最后一个有效镜头。
3. 选择该镜头末尾合适的 1–2 秒作为下一段开头。
4. 把青色生成选区的起点放在这段重叠内容的起点。
5. 将该视频片段的用途设为 **固定 Guide**。
6. 确认青色选区开头与视频重叠，并记录界面显示的 `GUIDE N帧`。
7. 如果需要延续上一段原声，开启“视频原声”；不需要时关闭。

假设上一段长 10 秒、重叠 2 秒、下一段生成 10 秒，则：

```text
上一段视频：时间轴 00:00–00:10
青色选区：时间轴 00:08–00:18
固定 Guide：生成结果局部时间 00:00–00:02
真正新增内容：生成结果局部时间 00:02–00:10
```

### 4.4 为下一段重写提示词

这是整个流程最重要的规则：

> 下一段提示词中的 `[Shot 1]` 必须先描述固定 Guide 中已经存在的上一段最后镜头，而不是直接描述新的剧情镜头。

原因是模型会把固定或参考的开头视频理解成本段的第一个镜头。如果 Agent 把新剧情直接写成 `[Shot 1]`，提示词与固定画面发生冲突，新剧情描述很容易失效。

正确写法分两种情况。

#### 情况 A：重叠之后仍然是同一个连续镜头

`[Shot 1]` 先准确复述固定重叠中的画面，然后说明固定区结束后动作如何自然继续。不要为了分段生成而人为制造剪辑点。

```text
[Shot 1] The shot opens on the exact continuation state preserved by the fixed guide: ...
During the fixed first 2.000 seconds, the character remains ... . After 00:02.000, the same uninterrupted shot continues as ...
```

#### 情况 B：重叠结束处本来就应该切镜头

`[Shot 1]` 描述固定重叠；新的镜头从实际切点开始写成 `[Shot 2]`。

```text
[Shot 1] ...
[Shot 2] At 00:02.000, the shot cuts to ...
```

不得为了让新内容成为 Shot 1 而忽略、隐藏或错误描述固定 Guide。

### 4.5 生成、检查并进入下一轮

每段生成后至少检查：

- Guide 区是否与上一段对应帧一致；
- Guide 结束后人物有没有瞬间换脸、换装或改变体型；
- 人物位置、朝向、视线和手中物体是否连续；
- 环境布局、光线方向和相机轴线是否连续；
- 动作速度和运镜方向是否延续；
- 对白、口型、环境声、音乐节拍和音量是否发生跳变；
- 新增内容是否从正确的局部时间开始。

检查合格后，取当前结果的最后一个镜头建立下一轮固定 Guide，重复上述流程。

## 5. 合并规则：必须删除重复 Guide

设第 `k` 段开头有 `F` 帧固定 Guide：

```text
Master = Segment 1
Master = Master + Segment 2[F:]
Master = Master + Segment 3[F:]
……
```

实际执行时：

1. 第一段完整保留。
2. 第二段及后续片段删除开头的固定 Guide 帧。
3. 视频裁切使用导演台显示的实际 `GUIDE N帧`，不要只根据肉眼估算秒数。
4. 24 FPS 下，音频切点应与删除的视频帧时间严格一致。
5. 合并后检查边界前后至少 1 秒，确认没有重复动作、重复台词或画面跳变。
6. 若音频切口产生爆音，可以在不重复对白的前提下做极短等功率交叉淡化；不能通过保留重复音频来掩盖接缝。

如果固定 Guide 为 48 帧，则后续片段从第 49 帧对应的内容开始保留；实现工具若使用从 0 开始的索引，则保留切片通常写作 `[48:]`。

## 6. 参考素材策略

### 6.1 每一段素材不同时

严格按照作者对当前段的要求选择素材。不要为了“保持一致”把所有历史素材永久堆进每一次生成：

- 只保留当前段真正需要的角色、场景、动作、风格和声音参考；
- 新角色或新场景在首次出现的片段加入对应素材；
- 不再出现的素材应从当前段移除，避免模型产生错误关联；
- 如果作者指定某个素材只提供服装、动作、运镜或音色，必须在 `subject_definitions` 和 `retention_analysis` 中写清楚其作用。

### 6.2 没有新参考素材，但场景没有变化

必须使用上一段最后一个镜头作为连续性参考。优先使用最后一个镜头末尾的 1–2 秒固定 Guide，而不是只依赖文字回忆人物站位和环境。

提示词还必须显式复述：

- 景别、机位高度、焦段观感和相机朝向；
- 每个人物在画面中的左右、前后和远近位置；
- 人物姿态、视线、表情与当前动作阶段；
- 关键道具的位置和持有关系；
- 场景布局、光线方向、色温和时间状态；
- 上一段结尾正在持续的环境声、对白或音乐状态。

### 6.3 三种视频用途的选择

| 模式 | Agent 何时使用 |
| --- | --- |
| **固定 Guide** | 长视频连续生成的默认模式。需要逐帧锁定上一段尾部，保证接缝稳定。 |
| **可编辑参考** | 需要替换人物、服装、风格或其他原画面内容时。它提供视频参考但不硬锁原人物。 |
| **仅固定边界** | 只要求首尾构图或边界状态一致，不希望中间整段被锁定时。 |

如果本段任务是在参考动作基础上替换人物，不要把需要替换的人物区域设为固定 Guide。可以把替换动作安排在固定 Guide 结束之后，或者根据作者要求改用“可编辑参考”。

## 7. 素材顺序和标签规则

Agent 不得根据文件名猜测 H3 输入编号，必须读取导演台底部实际显示的“提示词编号”。

- `<Picture 1>` 对应 `ref_image_0`，后续依次递增；
- `<Audio 1>` 对应 `ref_audio_0`，后续依次递增；
- 图片和独立音频可直接拖拽卡片调整顺序；
- 删除、重新上传或拖拽排序后，必须重新读取编号并更新提示词；
- `<Video N>` 由当前时间线和生成选区的实际参考计划产生；
- 固定 Guide 本身不一定占用 `<Video N>` 标签，是否存在可引用的视频标签以界面底部提示为准；
- `<Video N>` 和 `<Audio N>` 分别独立编号，编号相同不代表来自同一个文件；
- 视频文件包含声音，不代表提示词里一定存在 `<Audio N>`。只有启用并实际传入的音频才可引用。

提交前逐个核对：

```text
界面 <Picture 1> == 提示词 <Picture 1> == ref_image_0
界面 <Audio 1>   == 提示词 <Audio 1>   == ref_audio_0
界面 <Video 1>   == 提示词 <Video 1>   == 当前计划中的第一个普通视频参考
```

## 8. 音频连续和延长

音频必须与画面分段策略同时规划，不能在视频全部生成后再临时拼凑。

### 延续上一段真实原声

- 开启“视频原声”；
- 固定 Guide 区携带对应的同步原声；
- 在提示词中准确说明是 `audio reuse`、`audio reference`，还是仅延续环境声、音色或节奏；
- 合并时删除后续片段开头与 Guide 对应的重复音频。

### 只参考音色、音乐风格或节奏

- 如果不需要上一段视频的真实声音，关闭“视频原声”；
- 上传独立参考音频；
- 在 `subject_definitions` 中定义其具体职责；
- 在 `retention_analysis` 中使用官方音频关系：`fully_copy`、`partially_copy`、`reference` 或 `weak_reference`；
- 只参考音色时，不要复制参考音频中的原台词。

### 对白跨段

- 尽量让分段点落在一句对白结束之后；
- 必须跨段时，重叠区要覆盖可识别的语气和嘴型状态；
- 同一个说话者在各段中保持稳定的人物语义映射；
- 每次生成内部按本段实际发声顺序使用 `(S1)`、`(S2)`，同时在全局计划中记录人物与局部 ID 的映射；
- 对白和歌词只能写在 `detailed_description` 的 `<d>[Language] ...</d>` 中。

## 9. 后续片段的 Ref2VA 提示词模板

下面是结构模板，不是可直接复制的最终提示词。`<Video 1>` 和 `<Audio 1>` 只有在导演台实际显示这些标签时才能使用。

```text
subject_definitions:
<Subject 1> is [the continuing character, including identity, clothing, body proportions, and current state] from <Video 1>.
<Subject 2> is [the continuing environment and its spatial, lighting, and time-of-day properties] from <Video 1>.
<Audio 1> is [the synchronized continuation / voice-timbre / ambience / music reference, with its exact intended role].

summary:
[video continuation + audio reference] The target video begins by preserving the fixed overlap from the end of <Video 1>, then continues ...

retention_analysis:
<Subject 1> (appears in [Shot 1], ...): fully_preserved - ...
<Subject 2> (appears in [Shot 1], ...): fully_preserved - ...
<Video 1> (continuation state and temporal context): fully_preserved - ...
<Audio 1>: reference - ...

detailed_description:
[Style sentence in English.]
[Shot 1] The shot opens on the exact continuation state preserved by the fixed guide. [Describe composition, every subject's position, environment, lighting, current action phase, camera motion, and synchronized sound in the overlap.] During the fixed first 2.000 seconds, ... . After 00:02.000, the same continuous shot develops as ...
[Shot 2] At 00:06.000, the shot cuts to ...

overall_soundscape:
[Describe continuous ambience and physical sounds, including the exact reference/copy relationship where applicable.]

non_diegetic_music:
[Describe instrumentation, tempo, dynamics, and reference/copy relationship, or write N/A.]
```

如果界面没有 `<Video 1>`，删除模板中所有 `<Video 1>` 引用，但仍要在 `[Shot 1]` 准确描述固定 Guide。不得创造不存在的参考标签。

## 10. Agent 执行伪代码

```text
read_author_requirements()
install_or_read_official_h3_prompt_skill()
build_global_shot_and_audio_plan()

master = generate_segment_1(with required references)
validate(master)

while master.duration < target_duration:
    overlap = choose_last_stable_shot_tail(master, recommended=1_to_2_seconds)
    load_previous_segment_into_timeline()
    set_overlap_as_fixed_guide(overlap)
    select_only_current_segment_references()
    verify_visible_picture_video_audio_labels()
    write_ref2va_prompt_with_overlap_as_local_shot_1()
    next_segment = generate_and_validate()
    guide_frames = read_actual_guide_frame_count_from_director()
    master = concatenate(master, next_segment[guide_frames:])
    verify_visual_and_audio_seam()

trim_to_exact_target_duration_if_required()
final_quality_check()
```

## 11. 提交生成前的强制检查表

- [ ] 已阅读官方 `h3-prompt-writing` Skill 和 `ref-en.txt`。
- [ ] 提示词包含且只包含六个官方字段，顺序正确。
- [ ] 提示词主体为英文；对白、歌词、画面文字保留原语言。
- [ ] 当前段时长在 4–15 秒内。
- [ ] 所有参考素材数量和总时长符合 H3 限制。
- [ ] 当前段素材与作者要求一致，没有无关历史素材。
- [ ] 图片、视频、音频标签与导演台底部显示完全一致。
- [ ] 后续片段的 `[Shot 1]` 已先描述固定 Guide，而不是直接写新剧情。
- [ ] 同一镜头连续时没有人为在 Guide 结束点添加切镜；确实需要切镜时才创建 `[Shot 2]`。
- [ ] 场景未变化且没有新素材时，已使用上一段最后镜头作为固定 Guide。
- [ ] 已决定视频原声是开启、关闭、复制还是仅作参考。
- [ ] 已记录实际 `GUIDE N帧`，用于后续去重叠合并。
- [ ] 生成后已检查人物、场景、动作、运镜和音频接缝。
- [ ] 合并时已删除后续片段开头的重复 Guide 视频和音频。

## 12. 禁止事项

- 禁止忽略上一段参考画面，却把新增剧情直接写成下一段 `[Shot 1]`。
- 禁止使用导演台未显示的 `<Picture N>`、`<Video N>` 或 `<Audio N>`。
- 禁止把固定 Guide 重复保留在最终合并视频中。
- 禁止仅删除重复画面而保留重复音频。
- 禁止在人物替换区域使用会锁死原人物的整段固定 Guide。
- 禁止让每一段长期携带所有历史参考素材。
- 禁止猜测听不清的对白；按照官方 Skill 使用 `[unclear]`。
- 禁止把提示词写成剧情摘要而缺少逐镜头构图、位置、动作、镜头和声音信息。

---

本规范解决的是 Agent 如何使用时间线导演台编排长视频。插件负责组织当前一次生成的参考素材、固定 Guide、音频和标签；Agent 仍然负责全片规划、逐段提示词、质量筛选、循环生成以及最终去重叠合并。
