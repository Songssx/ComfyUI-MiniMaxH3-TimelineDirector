# MiniMax H3 直接 Latent 循环长视频

这是一个实验性长视频方案。它使用 ComfyUI PR #15923 提供的 `Loop`、`Loop Variable` 和 `Accumulate Save Video`，把上一段**采样后的完整 H3 视频+音频 latent**作为循环变量传给下一段。

## 为什么使用 Latent 反馈

普通续写会把上一段解码成 RGB，再把末尾帧重新编码为 Guide。反复执行时，每一轮都会增加一次 VAE 往返，微小的颜色和细节误差可能逐段累计。

直接 Latent 循环采用下面的数据流：

```text
上一段 sampled H3 AV latent
        │
        ├──完整 latent──> Loop Variable──> 下一轮
        │                                  │
        └──解码成片                         └──截取尾部 22 帧 latent
             │                                    │
             └──第二段起删除开头 22 帧 <──下一段第 0 帧固定 Guide
```

上一段只为输出视频解码，下一段 Guide 不读取解码后的 RGB。

## 节点连接

1. `Loop` 设置 `simple`，循环次数等于计划生成的片段数。
2. `Loop.iteration` 连接到：
   - `MiniMax H3 循环分段提示词.iteration`
   - `Loop Variable.iteration`
   - `MiniMax H3 Latent 循环续段.iteration`
   - `MiniMax H3 循环片段去重.iteration`
3. `Loop.is_first` 连接到 `MiniMax H3 Latent 循环续段.is_first`。
4. 本轮编码器输出的 `positive`、目标 `Latent` 先进入 `MiniMax H3 Latent 循环续段`，再进入采样器。
5. 采样器的完整 sampled latent 同时连接：
   - 视频、音频 VAE 解码；
   - `MiniMax H3 循环片段去重.sampled_latent`。
6. `循环片段去重.反馈 latent` 连接到 `Loop Variable.next_value`。
7. `Loop Variable.current_value` 连接到 `Latent 循环续段.previous_latent`。
8. 去重后的画面和音频进入 `Create Video`，再进入 `Accumulate Save Video`；`Loop.is_last` 连接其 `last`。

本轮的 `positive` 和目标 `Latent` 可以来自原生 `MiniMax H3 Image to Video`，也可以来自本插件的 `MiniMax H3 规划编码器`或兼容导演台。使用规划编码器时，把“循环分段提示词”的本段提示词输出连接到编码器的 prompt。

## 提示词规则

`segment_prompts` 支持 JSON 字符串数组，或使用独占一行的 `--- SEGMENT ---` 分隔。提示词数量少于循环次数时会重复最后一段。

需要交给视频生成 Agent 自动书写时，请使用更完整的 [循环分段提示词 Agent 规范](AGENT_H3_LOOP_PROMPT_WRITING_CN.md)。

每段都应使用标准 H3 结构，并至少包含：

```text
integrated_multimodal_description:
[Shot 1] ...
overall_soundscape:
...
non_diegetic_music:
...
```

第一段的 `[Shot 1]` 描述真实开场。第二段起，`[Shot 1]` 必须先承接上一段末尾固定区，再描述新动作。节点可以自动插入固定区声明，但每段正文仍要保持人物站位、环境、镜头运动、灯光、色彩和声音的连续性。

## 帧数与最终时长

H3 多帧 Guide 必须符合 `17k+5`。请求的重叠帧会自动向下对齐，例如：

- 24 → 22 帧；
- 40 → 39 帧；
- 小于 5 → 1 帧。

若每段 124 帧、重叠 22 帧、共 3 段，最终帧数为：

```text
124 + (124 - 22) + (124 - 22) = 328 帧
```

24fps 下约为 13.667 秒。音频按同一时间长度裁掉，避免重叠声重复。

## 当前限制

- PR #15923 仍是草案功能，ComfyUI 正式版接口变化后需要重新验证。
- 前后两段必须使用相同分辨率和 H3 latent 空间尺寸。
- 循环变量保存上一段完整 sampled latent；输出视频由 `Accumulate Save Video` 边生成边编码，避免把所有解码帧同时留在内存。
- 直接 latent 能减少 VAE 往返误差，但不会自动解决提示词漂移、采样随机性或模型自身的长期身份漂移。

## 已验证结果

测试环境：RTX 5090、PyTorch 2.11.0+cu130、PR #15923 当前分支、MiniMax H3 Ref2VA、640×352、每段 124 帧、8 步、重叠 22 帧、3 次循环。

结果：循环完成，输出 H.264/AAC MP4 为 328 帧、13.667 秒，视频和音频重叠均已去重。可复现脚本：`tests/experiments/run_minimax_h3_latent_loop.py`。
