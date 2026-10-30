# 破绽 / Loose Thread

**中文** · 一款中文优先、中英双语的 AI 推理游戏：用自然语言审问嫌疑人，从证词的破绽中找出犯人。
每个案件由程序生成并经求解器验证唯一可解；NPC 的台词由大模型说出，但它在结构上接触不到不该说的真相。

**English** · A Chinese-first, bilingual deduction game: interrogate suspects in natural language and
find the culprit through the loose threads in their testimony. Every case is procedurally generated
and checked by a solver to have exactly one solution; NPC lines are voiced by an LLM that is
structurally unable to see the truth it must not reveal.

> Status: pre-alpha (Phase 0 — skeleton and design). Nothing is playable yet.
> 状态：预览前阶段（P0：骨架与设计），暂不可玩。

## Development / 开发

```bash
uv sync --extra dev
uv run pytest
```

## License / 许可

Code: MIT (`LICENSE`). Content packs, experiment data and media: CC BY 4.0 (`LICENSE-CONTENT.md`).
