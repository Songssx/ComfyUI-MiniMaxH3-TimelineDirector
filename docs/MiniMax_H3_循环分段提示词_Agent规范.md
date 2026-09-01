# MiniMax H3 循环分段提示词 Agent 规范

本规范用于指导视频生成 Agent 为 `MiniMax H3 循环分段提示词`节点生成可直接解析的多段 Ref2VA 提示词。

## 1. Agent 的任务

根据用户提供的剧情、分段数量、每段时长、重叠帧数、参考素材清单及上一段结尾状态，为每次循环分别编写一条完整的 MiniMax H3 Ref2VA 提示词。

最终结果必须能直接粘贴进 `segment_prompts`，不得要求用户再次删除说明文字或修改格式。


### 1.1 生成前必须从用户输入中提取的时间参数

在开始编写任何分段提示词之前，Agent 必须先从用户当前任务文字、节点参数说明或明确给出的生成设置中识别并确认以下参数：

- `segment_duration_seconds`：每一段视频的完整生成时长，单位为秒；
- `actual_overlap_frames`：每一段向后传递给下一段作为 Latent Guide 的实际参考帧数；
- `fps`：用于计算重叠时长的帧率。本工作流默认按 24 fps 计算；如果用户明确提供其他帧率，则必须使用用户提供的帧率；
- `segment_count`：有限分段规划的总段数。

这些参数不是提示词中的装饰信息，而是决定镜头时间轴结构的核心输入。Agent 不得先写剧情再随意安排重叠区，而应先完成时间计算，再安排每一段的镜头与剧情。

如果用户明确写出类似：

```text
分成 3 段，每段 15 秒，每段向后参考 48 帧
```

则 Agent 必须解析为：

```text
segment_count = 3
segment_duration_seconds = 15.000
actual_overlap_frames = 48
fps = 24
overlap_seconds = 48 / 24 = 2.000
overlap_start = 15.000 - 2.000 = 13.000
overlap_end = 15.000
```

因此每一段用于传给下一段的最终 Guide 区间必须是：

```text
00:13.000-00:15.000
```

下一段开头必须把这 48 帧完整作为自己的 `[Shot 1]`：

```text
[Shot 1] During 00:00.000-00:02.000, ...
```

这里的 `00:00.000-00:02.000` 与上一段的 `00:13.000-00:15.000` 表示同一段画面与声音，只是两段提示词各自使用本段局部时间。

如果用户没有明确给出“每段时长”或“向后参考帧数”，而这两个参数会影响分段提示词时间轴，Agent 不得自行猜测固定值。应先向用户确认缺失参数，再生成正式提示词。

### 1.2 最后重叠镜头必须由参考帧数反推

对于除最终段以外的每一段，Agent 必须根据 `actual_overlap_frames` 反推出本段最后的重叠区：

```text
overlap_seconds = actual_overlap_frames / fps
overlap_start = segment_duration_seconds - overlap_seconds
overlap_end = segment_duration_seconds
```

上一段的最终重叠区必须被设计为一个清晰、可独立描述、可稳定延续的镜头状态。推荐将它单独写成最后一个 Shot，并且其开始时间严格等于 `overlap_start`。

例如：

```text
segment_duration_seconds = 15
actual_overlap_frames = 48
fps = 24
```

则上一段最后一个镜头应从：

```text
[Shot N] At 00:13.000, ...
```

开始，并持续到 `00:15.000`。

这个最后 2 秒镜头的提示词必须明确描述：

- 当前镜头构图和景别；
- 摄像机位置、方向、焦距感和运动状态；
- 每个主要人物在画面中的准确位置；
- 人物姿势、手部状态、头部角度、视线方向；
- 当前动作所处的具体相位，而不是只写“正在动作”；
- 人物表情和情绪状态；
- 场景中关键道具的位置与状态；
- 灯光方向、亮度、颜色和重要魔法/特效状态；
- 环境声、动作声、对白尾音及音乐当前相位；
- 哪些状态必须保持到本段结束，以便下一段稳定承接。

不得在最后的重叠镜头中塞入过多新剧情、快速连续动作或无法稳定保持的复杂状态。它首先是“上一段结尾”，同时也是“下一段开头的固定 Guide”。

### 1.3 下一段 `[Shot 1]` 必须逐项复现上一段最后重叠镜头

从第二段开始，`[Shot 1]` 的职责不是重新介绍剧情，而是完整描述上一段最后 `actual_overlap_frames` 帧中已经存在的画面与声音。

因此：

```text
上一段：
[Shot N] At 00:13.000, [最后 2 秒状态]

下一段：
[Shot 1] During 00:00.000-00:02.000, [同一状态]
```

两处必须在以下方面逐项一致：

- 人物身份与参考标签；
- 人物站位、姿势、表情和视线；
- 动作相位；
- 场景与道具状态；
- 摄像机位置、构图和运动；
- 灯光、颜色、特效；
- 环境声、对白尾音和音乐相位。

下一段 `[Shot 1]` 不得提前加入上一段最后重叠区中不存在的新动作、新台词、新人物位置或新镜头构图。

重叠区结束后：

- 如果镜头没有切换，继续在 `[Shot 1]` 中写：
  `From 00:[OVERLAP_END], without a cut, ...`
- 如果重叠结束后真实切镜，则从：
  `[Shot 2] At 00:[OVERLAP_END], ...`
  开始新镜头。

例如 48 帧、24 fps 时：

```text
[Shot 1] During 00:00.000-00:02.000, [完整复现上一段最后 48 帧].
[Shot 2] At 00:02.000, the camera cuts to...
```

### 1.4 剧情分配必须服从“有效新增时长”

对于第二段及后续段，前 `overlap_seconds` 秒已经被上一段 Latent Guide 占用，因此真正可用于推进新剧情的时间为：

```text
new_content_seconds = segment_duration_seconds - overlap_seconds
```

例如每段 15 秒、向后参考 48 帧、24 fps：

```text
overlap_seconds = 2.000
new_content_seconds = 13.000
```

也就是说：

- 第一段可以从 `00:00.000` 开始完整推进剧情，但最后 `00:13.000-00:15.000` 必须同时承担下一段 Guide 的职责；
- 第二段及后续段的 `00:00.000-00:02.000` 是上一段已有内容，不应重复计算为新的剧情容量；
- 真正的新剧情从 `00:02.000` 后开始；
- 同时，本段自己的 `00:13.000-00:15.000` 又要作为下一段 Guide。

因此，Agent 在拆分长剧情时必须根据“有效新增时长”安排台词、动作和切镜，避免把过多对白塞进实际只有十几秒的新内容区间。

### 1.5 控制剧情密度并保持电影化叙事

循环分段视频的剧情容量必须根据当前任务的实际分段数量、单段时长、重叠时长和有效新增总时长动态确定，不得预设任务一定是四段、30 秒或其他固定规模。在有效时长较短时，应围绕一个清晰的核心处境或核心事件展开，不得把多个相互独立的剧情节点连续压缩进有限时长；只有在有效新增总时长足够、前后因果能够清楚呈现时，才可以扩展为多个连续事件。

例如，当任务为四段且有效新增内容总计约 30 秒时，通常应选择一个事件进行细致呈现，如只表现“陷入流沙并设法脱困”，而不是同时加入寻找地图、寻找宝藏、陷入流沙、打开宝箱和遭遇怪物等完整事件链。该示例仅用于说明剧情密度，不构成对分段数量、总时长或题材的固定要求。

Agent 必须根据实际可用时长控制叙事容量：

- 多个视频分段应共同完成一条或多条与实际有效时长相匹配的连续动作线或情绪线。Agent 应根据 `segment_count` 动态划分建立、发展、变化和结果等阶段，不得机械套用固定的四段结构；
- 不要求每个 Shot 都安排人物讲话。对白只在确实推动人物关系、决策或情绪时出现，避免把镜头写成轮流说话的台词清单；
- 应适当使用环境空镜、处境镜头、动作细节、人物反应、道具状态和视觉效果镜头，让观众看懂危险、空间关系和状态变化；
- 环境镜头和效果镜头必须服务于当前核心事件及前后连续性，不得借机引入新的任务、地点、敌人或剧情目标；
- 应为动作过程、反应、停顿和情绪余韵保留足够时间，使事件在画面中真正发生，而不是只用快速切镜告知结果；
- 相邻分段必须延续同一处境中的人物位置、动作因果、情绪强度、环境变化和未完成目标，不得在没有铺垫的情况下跳到新的剧情阶段；
- 避免在短时长内密集使用“发现—转折—新危险—再转折—新目标”的预告片式结构。最终成片应呈现一个被完整观察和推进的电影段落，而不是多个剧情卖点的蒙太奇预告。

Agent 应先计算当前任务的有效新增总时长：第一段按完整时长计入，后续各段仅计入 `segment_duration_seconds - overlap_seconds`；如果各段时长不同，则逐段计算后求和。随后再据此评估能够清楚表达的事件数量、对白量、动作复杂度和镜头数量。

当用户提供的剧情信息超过当前有效新增总时长能够清楚表达的容量时，Agent 应主动收窄范围，选择最重要的内容做细致展开，并保持其起因、过程、人物反应和结果连贯。当分段数量更多或有效时长更长时，可以逐步扩展支线或新增事件，但每个新增事件都必须具有足够的铺垫、过程和结果，并与前后分段自然衔接。

### 1.6 最终段的处理

如果当前段是整个任务的最后一段，并且后面不会继续生成，则不强制为了下一段而预留一个 Guide 镜头。

但如果用户的工作流仍会统一输出最后 `actual_overlap_frames` 帧，或者用户明确要求最后一段也保持可继续扩展，则最后一段仍应按照相同规则，在末尾设计一个稳定的独立镜头状态。


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
- 分段块数量必须等于“有限分段展开”的分段数量。

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
- 插件内部传递的上一段 Latent Guide 不占用 `<Video N>`、`<Audio N>` 或 `<Picture N>` 编号。

如果一张图片只定义人物、服装、场景或风格，应在对应 `<Subject N>` 中引用该图片，不必额外把图片定义成独立关键帧。只有图片本身作为首帧、尾帧、关键帧或构图锚点时，才单独定义 `<Picture N>`。

### 4.1 人物只在首次出场或确有变化时定义

人物视觉参考采用“首次建立、后续继承、变化时局部更新”的原则：

- 某个人物第一次进入故事时，使用对应 `<Picture N>` 建立一次完整身份，包括外貌、体型、发型、服装和可辨识配饰；
- 第二段及以后，如果该人物已经存在于开场 Latent Guide 中，人物身份直接继承上一段，不重复粘贴整套外貌和服装定义；
- 后续段的 `subject_definitions` 只定义本段首次出场的人物、本段新增的独立素材，以及实际启用的音频参考；
- 已继承人物只有在服装、年龄状态、造型或身份设定发生明确变化时，才补充发生变化的属性，稳定属性继续沿用；
- 为每个主要人物建立稳定的故事称呼，例如 `the girl`、`the pig`、`the little witch`，后续所有 Shot 沿用同一称呼，不用近义词把同一人物再次介绍成新主体；
- 某人物连续离开若干分段后重新入画，且已经不在当前开场 Latent Guide 中时，在重新入画的分段使用其原参考图做一次身份校准；后续分段继续继承；
- 某人物的参考图虽然仍连接在素材规划台，但本段画面和声音均未使用该人物时，不因素材存在而写入本段提示词；
- 多视图人物设定图中的正面、侧面、背面和特写共同描述同一个人物身份，首次定义时应明确它们是同一角色的不同视角；
- 参考音频只负责音色和说话特征。后续段使用音色时，将 `<Audio N>` 绑定到 Latent Guide 中已经存在的同一人物，无需再次定义该人物的视觉身份。

推荐的后续段定义方式：

```text
subject_definitions:
<Audio 2> is the voice reference for the same pig character already carried into the opening Latent Guide, preserving his established vocal timbre and speaking manner.
```

如果工作流在每一段都自动挂载相同人物图片，则把图片写成对开场 Latent 中既有人物的身份校准，而不是一次新的角色建立：

```text
<Subject 1> is the girl already visible in the opening Latent Guide; <Picture 1> calibrates her established facial identity, hairstyle, clothing, and proportions for this segment.
```

### 4.2 用正向构图控制人物数量

提示词应直接描述镜头中真实可见的画面，用人物清单、空间位置、景别和遮挡关系固定构图。人物数量通过“画面里有什么”来控制，而不是反复描述“画面里没有什么”。

- 每个 Shot 开头先写清当前可见人物及其位置，例如：`The girl sits on the right side of the sofa, the pig stands beside the left armrest, and the little witch stands behind the coffee table.`；
- 单人特写使用主体占画面的方式描述，例如：`A tight shoulder-up close-up centers on the little witch, with the softly blurred curtains filling the background.`；
- 双人或多人镜头按左、中、右或前景、中景、后景逐一安排人物，并明确视线关系；
- 人物离开镜头时，通过镜头新的正向构图描述当前主体，例如从全景切到小巫师特写，直接写小巫师的景别、位置和背景；
- 群像场景将军队、观众或路人写成环境群体，把主要人物单独绑定到参考身份，避免让一张主角参考图承担整个群体的身份；
- `summary`、`retention_analysis` 和 `detailed_description` 均只写本段实际使用的参考关系与画面内容。

优先采用以下写法：

```text
[Shot 2] At 00:03.200, a tight shoulder-up close-up centers on the little witch. Her face fills the frame, her wand enters from the lower-right foreground, and the warm curtains form a soft background.
```

避免把下面这类缺席信息和限制语句反复写进镜头描述：

```text
Do not create extra characters. The girl and the pig must not appear. No silhouettes or background people.
```

只有当某个生成瑕疵无法通过人物清单、构图、景别和空间关系解决时，才允许在整段提示词中加入一次简短技术约束；镜头正文仍以正向画面描述为主。

### 4.3 降低跨段重复人物风险的 Guide 设计

除最终段外，每段结尾的 Guide 镜头还应满足以下人物稳定性要求：

- 需要延续的人物在 Guide 中具有清晰、可分离的轮廓和稳定站位；
- 人物之间保留合理空间关系，减少大面积互相遮挡、快速交叉和瞬间进出画面；
- Guide 区采用容易复现的中低速动作相位、稳定景别、稳定灯光和明确视线方向；
- 强烈魔法、爆炸、闪光、快速旋转或复杂遮挡可以先完成主体变化，再让 Guide 区落到清晰可承接的状态；
- 下一段 `[Shot 1]` 用正向人物清单逐项复现 Guide 中可见人物的数量、位置、姿态、表情、朝向和动作相位；
- 新人物在重叠结束后的真实入画时刻首次定义并进入构图，使既有人物继承与新人物登场在时间上清楚分开。

## 5. 六个字段的写作要求

### `subject_definitions`

逐行定义本分段首次建立或确实需要重新校准的 `<Subject N>`，以及本段实际使用的独立关键帧 `<Picture N>`、结构来源 `<Video N>` 和 `<Audio N>`。已经由开场 Latent Guide 稳定继承的人物不重复写完整视觉定义；若本段只调用其音色，只定义并绑定对应 `<Audio N>`。同一标签在本分段六个字段中必须始终表示同一内容。

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
- 没有实际切镜时，不要仅为动作变化创建新 Shot；
- 每个 Shot 用正向构图写清实际可见的人物、景别、位置、朝向和相互关系；
- 通过明确当前画面内容控制人物数量，避免连续堆叠“谁不出现”“不得出现谁”等缺席性描述。

### `overall_soundscape`

用一至四句英文总结环境声、物理动作声和非语言人声。不要在这里重复完整对话或歌词。

### `non_diegetic_music`

描述只有观众能听见的配乐，包括乐器、速度、节奏和动态变化。没有画外配乐时写 `N/A`。

## 6. 第一段写法

第一段没有上一段 Latent Guide，应按正常 Ref2VA 视频开场书写：

- `[Shot 1]` 从真正的故事开场开始；
- 明确初始构图、人物站位、环境、灯光、镜头运动和声音；
- 在人物首次出场处完成其视觉身份定义，并保持参考图与对应音色绑定一致；
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


重叠区不仅决定下一段开头，也反向决定上一段最后一个镜头的起始时间。必须同时计算：

```text
overlap_start = segment_duration_seconds - overlap_seconds
```

例如每段 15 秒、实际重叠 48 帧、24 fps：

```text
overlap_seconds = 48 / 24 = 2.000 秒
overlap_start = 15.000 - 2.000 = 13.000 秒
```

则上一段最后的独立 Guide 镜头必须覆盖 `00:13.000-00:15.000`，下一段 `[Shot 1]` 必须覆盖同一内容对应的局部时间 `00:00.000-00:02.000`。

### 7.1 推荐模式：节点自动注入连续性声明

当 `inject_continuity_instruction = true` 时，节点会自动在第二段起的 `[Shot 1]` 后插入通用的固定 Latent 声明。Agent 不需要重复这句通用声明，但仍必须描述重叠区里实际可见和可听的内容：

```text
[Shot 1] During 00:00.000-00:00.917, <Subject 1> remains in the ending pose carried over from the preceding segment, with her right hand holding the blue sphere near chest height while the same slow camera push-in and room tone continue. From 00:00.917, without a cut, she lowers the sphere toward the desk...
```

通用声明只说明“必须连续”，不能代替对人物位置、动作相位、场景、镜头、灯光、颜色和声音的具体描述。

后续段开场中的人物以 Latent Guide 为身份来源。`[Shot 1]` 只需准确复现人物清单、位置、姿态、表情、朝向和动作相位，不再把每个既有人物按首次出场方式重新介绍一遍。

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
- 音色参考直接绑定到开场 Latent 中已经存在的同一人物，不触发人物视觉身份的重复定义；
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
[Define each visual character when that character first appears, plus the references actually used in segment 1. Treat every multi-view character sheet as one identity.]

summary:
[Task types] [Summarize segment 1 and its reference relationships.]

retention_analysis:
[One line for every actual reference label.]

detailed_description:
[Style sentence.]
[Shot 1] [True opening composition with a positive roster of visible characters, their positions, environment, actions, camera, lighting, and synchronized sound.]

overall_soundscape:
[Segment 1 ambience and physical sounds.]

non_diegetic_music:
[Music description or N/A.]

--- SEGMENT ---

subject_definitions:
[Define only newly introduced visual characters, genuinely changed visual attributes, active independent media, and active voice references. Bind voice references to the same characters carried by the opening Latent Guide.]

summary:
[video continuation + ...] [Summarize segment 2 and its reference relationships.]

retention_analysis:
[One line for every actual reference label.]

detailed_description:
[Continue the established style.]
[Shot 1] During 00:00.000-00:[OVERLAP_END], [positively enumerate the visible characters and describe their exact carried positions, poses, expressions, directions, action phases, environment, and framing from segment 1]. From 00:[OVERLAP_END], without a cut, [describe the new continuation action and the resulting visible composition].

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
13. 是否已从用户输入中明确取得每段时长、向后参考帧数、分段数量和所用 fps；若缺失关键参数，是否先询问而不是自行猜测。
14. 是否已正确计算 `overlap_seconds = actual_overlap_frames / fps`。
15. 是否已正确计算上一段最后 Guide 镜头的开始时间 `overlap_start = segment_duration_seconds - overlap_seconds`。
16. 除最终段外，每一段最后的 Guide 区是否被写成可稳定延续的独立镜头，并准确覆盖 `overlap_start` 到本段结束。
17. 第二段起 `[Shot 1]` 是否逐项复现直接上一段最后 Guide 镜头，而没有提前加入新动作、新台词或新构图。
18. 第二段起的新剧情容量是否按 `segment_duration_seconds - overlap_seconds` 估算，避免在重叠区重复推进剧情。
19. 人物参考图与对应音频标签是否严格一一匹配，同一人物不得误用其他角色的 `<Audio N>`。
20. 每个人物是否只在首次出场、明确造型变化或必要身份校准时写完整视觉定义。
21. 后续段中已经由 Latent Guide 继承的人物是否避免重复粘贴外貌、服装和身份定义。
22. 参考音频是否只绑定到既有人物的音色，而没有引发视觉人物的重复定义。
23. 多视图人物图是否被明确视为同一人物的不同视角。
24. 每个 Shot 是否以正向人物清单、位置、景别和空间关系描述实际画面。
25. 镜头正文是否避免反复堆叠“谁不出现”“不得出现谁”等缺席性描述。
26. Guide 区中的人物轮廓、站位、动作相位、灯光和景别是否稳定、清晰、便于下一段复现。
27. 群像人物是否作为环境群体描述，并与主要人物的独立参考身份清楚区分。
28. 最终是否只包含可直接粘贴进节点的提示词文本。

## 11. 给 Agent 的最终指令

可将下面这段作为任务末尾的强制输出约束：

> 按照 MiniMax H3 Ref2VA 六字段结构，为每次循环分别生成一条完整提示词。生成前必须先从用户输入中明确读取分段数量、每段时长、向后参考帧数以及所用 fps；默认仅在用户未另行指定 fps 时按 24 fps 计算。根据 `overlap_seconds = actual_overlap_frames / fps` 和 `overlap_start = segment_duration_seconds - overlap_seconds` 先确定每段的重叠时间轴。除最终段外，每一段最后 `actual_overlap_frames` 帧必须设计成一个可稳定延续的独立 Guide 镜头，并从 `overlap_start` 精确持续到本段结束。第二段起的 `[Shot 1]` 必须以正向人物清单逐项复现直接上一段最后 Guide 镜头中实际可见的人物数量、位置、姿态、表情、朝向、动作相位、构图、灯光、声音和音乐相位，再从重叠结束时间继续新动作或创建真实的新镜头。人物视觉身份遵循“首次建立、后续继承、变化时局部更新”：第一段或人物首次出场时完成定义，后续段由开场 Latent Guide 继承，不反复粘贴既有人物的完整外貌与服装定义；本段只定义首次出场的人物、明确发生变化的属性、实际使用的独立素材和音色参考。参考音频只绑定既有人物的音色，不触发视觉身份重建。所有镜头正文只描述真实可见的人物、位置、景别、环境和动作，通过正向构图控制人物数量，避免反复使用“画面不出现谁”“不得出现单独人物”等缺席性约束。Guide 区应保持人物轮廓清晰、站位可分离、动作相位与灯光稳定。使用独占一行的 `--- SEGMENT ---` 分隔相邻分段，分段数量必须等于循环次数。严格使用当前分段素材规划提供的 Picture、Video、Audio 编号，保证人物参考图与对应音色严格匹配，Latent Guide 不占用任何参考编号。若用户未提供会影响时间轴的每段时长或向后参考帧数，不得自行猜测，应先询问用户。最终只输出可直接粘贴进 `MiniMax H3 循环分段提示词`节点的纯文本，不输出解释、标题或 Markdown 代码围栏。
