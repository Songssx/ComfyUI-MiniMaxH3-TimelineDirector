# MiniMax H3 续段 Guide 色差 A/B 实验

本实验用于区分两种续段固定方式：

- **A / 原生 RGB Guide**：首段采样 latent → VAE Decode → 截取最后 22 帧 RGB →
  `MiniMaxH3AddGuide` 内再次 VAE Encode → 第二段采样。
- **B / 直接 latent Guide**：从首段采样结果直接截取最后 22 帧对应的 7 个 H3 视频
  latent token → 固定到第二段开头 → 第二段采样。

两条第二段分支共用相同提示词、目标空 latent、模型、LoRA、8 步 Euler 调度、随机噪声
和种子，只改变 Guide 的来源。实验分辨率为 640×352，首段与第二段均为 124 帧/24fps，
固定区为前 22 帧。音频未加入比较，避免产生额外变量。

## 复现

启动已安装本插件的 ComfyUI 后，将 `minimax_h3_latent_guide_ab_api.json` 作为 API prompt
提交到 `/prompt`。工作流需要 MiniMax H3 的 UNet、CLIP、视频 VAE，以及文件中指定的
Lightx2v Turbo LoRA。模型文件名可以按本机情况修改。

实验节点：

- `MiniMaxH3AddLatentGuide`：直接截取已采样 H3 视频 latent 的合法尾部时间块。
- `MiniMaxH3VisualDifferenceMetrics`：计算 MAE、MSE、PSNR、RGB 均值、平均饱和度和
  极值像素比例，并输出放大的绝对差异帧。

## 本次实测（2026-08-27）

Prompt ID：`45e75fb4-aa7d-42ef-86b7-a22d0a6698d7`

| 比较 | MAE | PSNR | 饱和度变化 | 极值像素比例变化 |
| --- | ---: | ---: | ---: | ---: |
| 单次 VAE 往返：源尾部 → Decode/Encode/Decode | 0.008184 | 37.881 dB | +0.010766 | +0.005583 |
| A 固定区相对源尾部 | 0.019335 | 30.551 dB | +0.021667 | +0.016311 |
| B 固定区相对源尾部 | 0.019573 | 30.624 dB | +0.005120 | +0.008588 |
| A 与 B 完整第二段 | 0.020322 | 26.509 dB | B 相对 A -0.017239 | -0.008428 |

这一次样本中，直接 latent Guide 没有做到像素级完全复现，但其固定区的饱和度偏移约为
RGB Guide 的 24%，极值像素增长也更小，支持“VAE 往返会参与色彩累计”的判断。由于
这是单个种子和单个场景的实验，不能据此断言所有场景都以相同比例改善；正式结论应至少
再跑多个种子、明暗场景和多轮续段。

视频输出保存在 ComfyUI 的 `output/video/H3_latent_ab/`，不会纳入 Git 仓库，避免增加
插件克隆体积。
