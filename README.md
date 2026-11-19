# 角色动画全链路 · Character Anim

> 给一张角色静图，本地跑出能循环的动画：GIF、WebP、PNG 帧条、MP4，一次出全套。全程本地，不花订阅费。

**关键词**：角色动画 · 图生视频 · sprite 生成 · 游戏角色动效 · 待机动画 · 行走动画 · 循环动画 · 透明 GIF · WebP 动画 · PNG 序列帧 · 数字人 · MiniMax H3 · 本地推理 · Character animation · sprite sheet · image to video · game asset

---

## 这是什么

把一张角色立绘变成可用动效的生产线：

1. **图生视频**：本地 MiniMax H3 把静图变成短视频
2. **切帧抠像**：切成透明序列帧
3. **找循环**：自动找首尾衔接的循环区间
4. **多格式输出**：GIF（发微信用）、WebP（网页用）、PNG 帧条（游戏引擎用）、MP4（预览用）

## 产出什么

| 格式 | 用途 |
|---|---|
| `*.mp4` | 深色底预览，看动作对不对 |
| `*.gif` | 透明底，微信/聊天场景 |
| `*.webp` | 透明底，网页体积小 |
| `*_strip.png` | PNG 帧条，直接喂游戏引擎 |
| `anim_report.json` | 每步实测耗时与产物路径 |

## 用法

```bash
python ./character_anim.py <角色图> --prompt "<动作描述>" -o <输出目录> --state <状态名>
```

例：

```bash
python ./character_anim.py "./角色正面.png" \
  --prompt "轻微呼吸，身体微微起伏，衣摆随风轻摆" \
  -o ./out --state idle
```

## 前置条件

- 本地已部署 MiniMax H3（见另一个仓库 `h3-local-deploy`）
- 需要 sprite 切帧工具链

## 设计取舍

- **只做循环**：待机、行走、挥手这类能首尾衔接的动作。非循环的一次性动作不适合这条链路。
- **全本地**：不上传外部服务。素材是你的，就跑在你自己机器上。
- **报告可追**：每一步的耗时与产物都写进 `anim_report.json`，出了问题能定位到是哪一步。

## 适用场景

- 游戏 NPC / 主角的待机、行走、挥手动画
- 网页吉祥物动图
- 数字人短循环
- 内容素材的动态化

## 授权

MIT License

## 联系

加微信：**enhaopang**

添加时请备注：GitHub-character-anim

> 不提供免费技术支持。问题请走 Issue。
