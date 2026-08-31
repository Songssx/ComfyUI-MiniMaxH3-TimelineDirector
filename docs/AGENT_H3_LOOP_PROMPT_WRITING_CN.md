# MiniMax H3 循环分段提示词 Agent 规范

本规范用于指导视频生成 Agent 为 `MiniMax H3 循环分段提示词`节点生成可直接解析的多段 Ref2VA 提示词。

## 1. Agent 的任务

根据用户提供的剧情、分段数量、每段时长、重叠帧数、参考素材清单及上一段结尾状态，为每次循环分别编写一条完整的 MiniMax H3 Ref2VA 提示词。

最终结果必须能直接粘贴进 `segment_prompts`，不得要求用户再次删除说明文字或修改格式。

## 2. 最终输出格式

只输出纯提示词文本，不输出解释、标题、序号说明、Markdown 代码围栏或“以下是结果”等前后缀。

不同分段之间使用下面这一行分隔：

```text
--- SEGMENT ---
```

分隔符必须：

- 独占一行；
- 全部使用英文大写 `SEGMENT`；
- 不得放在第一段之前或最后一段之后；
- 分段块数量必须等于 Loop 的循环次数。

不要在最终输出中使用 JSON，除非调用方明确要求 JSON 数组。分隔符格式更容易人工检查和修改。

## 3. 每个分段的固定结构

每个分段都必须是完整的 Ref2VA 提示词，并严格按以下顺序输出六个字段：

```text
subject_definitions:
...

summary:
...

retention_analysis:
...

detailed_description:
...

overall_soundscape:
...

non_diegetic_music:
...
```

六个字段名称不得翻译、改名、缺失或调换顺序。正文使用英文；对话、歌词和画面中真实可见的文字保留原语言。

## 4. 参考标签与顺序

提示词中的标签必须严格使用当前分段素材规划台显示的编号：

- `<Picture 1>` 对应当前分段的 `ref_image_0`；
- `<Video 1>` 对应当前分段的 `ref_video_0`；
- `<Audio 1>` 对应当前分段的 `ref_audio_0`；
- 同类素材继续按 2、3、4 顺序递增；
- 不得跳号、重复定义、交换顺序或引用不存在的编号；
- 不同类别分别编号，`<Video 1>` 和 `<Audio 1>` 不一定来自同一个文件；
- 只有实际启用的视频原声才会占用 `<Audio N>`；
- 上一段通过 `Loop Variable` 传递的 Latent Guide 不占用 `<Video N>`、`<Audio N>` 或 `<Picture N>` 编号。

如果一张图片只定义人物、服装、场景或风格，应在对应 `<Subject N>` 中引用该图片，不必额外把图片定义成独立关键帧。只有图片本身作为首帧、尾帧、关键帧或构图锚点时，才单独定义 `<Picture N>`。

## 5. 六个字段的写作要求

### `subject_definitions`

逐行定义本分段实际使用的 `<Subject N>`、独立关键帧 `<Picture N>`、结构来源 `<Video N>` 和 `<Audio N>`。同一标签在本分段六个字段中必须始终表示同一内容。

### `summary`

使用一个简短英文段落概括本分段及参考关系，并以前缀开头，例如：

```text
[reference generation] ...
[video continuation + reference generation + audio reference] ...
[video editing + audio reuse] ...
```

第二段及以后属于对前一段的延续时，应包含 `video continuation`。

### `retention_analysis`

每个实际参考标签写一行。视觉标签只使用：

- `fully_preserved`
- `partially_preserved`
- `attribute_transfer`
- `weak_reference`

音频标签只使用：

- `fully_copy`
- `partially_copy`
- `reference`
- `weak_reference`

不要为 Latent Guide 虚构 retention 条目。

### `detailed_description`

按播放顺序写清：构图、主体外观和位置、环境、灯光、动作、状态变化、镜头运动、当前声音，以及参考素材开始发挥作用的准确位置。

- 第一镜头写 `[Shot 1]`，不加开场时间戳；
- 后续真实切镜写 `[Shot N] At MM:SS.mmm, ...`；
- 所有时间戳使用当前分段自己的局部时间，从 `00:00.000` 重新计算；
- 时间戳必须严格递增并落在本段时长内；
- 没有实际切镜时，不要仅为动作变化创建新 Shot。

### `overall_soundscape`

用一至四句英文总结环境声、物理动作声和非语言人声。不要在这里重复完整对话或歌词。

### `non_diegetic_music`

描述只有观众能听见的配乐，包括乐器、速度、节奏和动态变化。没有画外配乐时写 `N/A`。

## 6. 第一段写法

第一段没有上一段 Latent Guide，应按正常 Ref2VA 视频开场书写：

- `[Shot 1]` 从真正的故事开场开始；
- 明确初始构图、人物站位、环境、灯光、镜头运动和声音；
- 不得写“continuation from the preceding segment”。

## 7. 第二段及后续段写法

后续段的开头已经被上一段末尾 Latent 固定。Agent 必须先把这段重叠内容当作当前分段的开场，再书写新增内容。

实际重叠秒数按下面计算：

```text
overlap_seconds = actual_overlap_frames / 24
```

例如实际重叠为 22 帧：

```text
22 / 24 = 0.917 秒
```

### 7.1 推荐模式：节点自动注入连续性声明

当 `inject_continuity_instruction = true` 时，节点会自动在第二段起的 `[Shot 1]` 后插入通用的固定 Latent 声明。Agent 不需要重复这句通用声明，但仍必须描述重叠区里实际可见和可听的内容：

```text
[Shot 1] During 00:00.000-00:00.917, <Subject 1> remains in the ending pose carried over from the preceding segment, with her right hand holding the blue sphere near chest height while the same slow camera push-in and room tone continue. From 00:00.917, without a cut, she lowers the sphere toward the desk...
```

通用声明只说明“必须连续”，不能代替对人物位置、动作相位、场景、镜头、灯光、颜色和声音的具体描述。

### 7.2 重叠结束后不切镜头

新动作继续属于 `[Shot 1]`：

```text
From 00:00.917, without a cut, ...
```

不要把同一个连续镜头强行拆成 Shot 2。

### 7.3 重叠结束后确实切镜头

固定重叠区是 `[Shot 1]`，新镜头从 `[Shot 2]` 开始：

```text
[Shot 1] During 00:00.000-00:00.917, the preceding final shot continues...
[Shot 2] At 00:00.917, the camera cuts to...
```

不要把用户真正想生成的新镜头错误地写成当前分段开头的 `[Shot 1]`，否则它会与固定 Guide 争夺同一时间范围。

### 7.4 后续段只承接直接上一段

第三段承接第二段末尾，第四段承接第三段末尾。不要让所有后续段反复回到第一段的初始构图和动作。

## 8. 音频连续性

当 `continue_audio_latent = true` 时，视频和音频 Latent 会一起延续。第二段起必须说明：

- `00:00.000` 至重叠结束时间内，上一段环境声、动作声、说话尾音或音乐相位连续；
- 新声音从重叠结束后自然进入；
- 不得从头重复上一段已经说完的整句台词；
- 如果同一句话跨段，保留同一 `(Sx)`，并使用 `<scenetrans>` 表示跨段连续；
- 只参考音色时，不得复制参考音频中的原台词；
- 完整对话格式为 `<d>[Chinese] 原始台词。</d>`，对话内容不得翻译或改写。

推荐写法：

```text
overall_soundscape:
During 00:00.000-00:00.917, the preceding room tone, movement sounds, and voice tail continue seamlessly. After 00:00.917, the same ambience remains while new action sounds enter naturally.
```

## 9. Agent 最终输出模板

Agent 应替换所有方括号占位内容，并直接输出完成后的纯文本：

```text
subject_definitions:
[Define only the references actually used in segment 1.]

summary:
[Task types] [Summarize segment 1 and its reference relationships.]

retention_analysis:
[One line for every actual reference label.]

detailed_description:
[Style sentence.]
[Shot 1] [True opening composition, subjects, environment, actions, camera, lighting, and synchronized sound.]

overall_soundscape:
[Segment 1 ambience and physical sounds.]

non_diegetic_music:
[Music description or N/A.]

--- SEGMENT ---

subject_definitions:
[Define only the references actually used in segment 2.]

summary:
[video continuation + ...] [Summarize segment 2 and its reference relationships.]

retention_analysis:
[One line for every actual reference label.]

detailed_description:
[Continue the established style.]
[Shot 1] During 00:00.000-00:[OVERLAP_END], [describe the exact carried ending state from segment 1]. From 00:[OVERLAP_END], without a cut, [describe the new continuation action].

overall_soundscape:
During 00:00.000-00:[OVERLAP_END], [describe continuous audio]. After 00:[OVERLAP_END], [describe the new sound development].

non_diegetic_music:
[Continuous music development or N/A.]
```

继续增加分段时，重复第二个完整六字段块，并把它改为承接直接上一段。

## 10. 输出前静默检查

Agent 在回答前必须自行检查，但不要把检查过程输出给用户：

1. 分段块数量是否等于循环次数。
2. 分隔符是否严格为独占一行的 `--- SEGMENT ---`。
3. 每段是否都有六个字段且顺序正确。
4. 每个引用标签是否存在、连续编号并与本段素材规划一致。
5. 是否错误地给 Latent Guide 分配了 `<Video N>` 或 `<Audio N>`。
6. 第一段是否没有虚构“上一段”。
7. 第二段起是否先描述固定重叠区，再描述新增内容。
8. 重叠结束时间是否等于实际重叠帧数除以 24。
9. 新镜头只有在真实切镜时才从 `[Shot 2]` 开始。
10. 所有时间戳是否使用本段局部时间且未超过本段时长。
11. 人物身份、站位、环境、镜头运动、灯光、颜色和声音是否与上一段末尾连续。
12. 音频是否避免重复台词和突然重启。
13. 最终是否只包含可直接粘贴进节点的提示词文本。

## 11. 给 Agent 的最终指令

可将下面这段作为任务末尾的强制输出约束：

> 按照 MiniMax H3 Ref2VA 六字段结构，为每次循环分别生成一条完整提示词。使用独占一行的 `--- SEGMENT ---` 分隔相邻分段。分段数量必须等于循环次数。第二段起先描述上一段 Latent Guide 固定的开头重叠区，再从重叠结束时间继续新动作或创建真实的新镜头。严格使用当前分段素材规划提供的 Picture、Video、Audio 编号，Latent Guide 不占用任何参考编号。最终只输出可直接粘贴进 `MiniMax H3 循环分段提示词`节点的纯文本，不输出解释、标题或 Markdown 代码围栏。
