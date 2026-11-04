# 破绽 / Loose Thread

**中文** · 一款中文优先、中英双语的 AI 推理游戏：用自然语言审问嫌疑人，从证词的破绽中找出犯人。
每个案件由程序生成并经求解器验证唯一可解；NPC 的台词由大模型说出，但它在结构上接触不到不该说的真相。

**English** · A Chinese-first, bilingual deduction game: interrogate suspects in natural language and
find the culprit through the loose threads in their testimony. Every case is procedurally generated
and checked by a solver to have exactly one solution; NPC lines are voiced by an LLM that is
structurally unable to see the truth it must not reveal.

> Status: before the first release (P4). Playable on your own machine.
> 状态：首次发布之前（P4）。可以在自己的电脑上试玩。

## Play / 试玩

```bash
uv run python -m loosethread.web
```

Open http://127.0.0.1:8000. The first run downloads the Pyodide runtime (about 6 MiB). It plays with no key, using rules
and template lines; you can add a DeepSeek key of your own for model-read questions and model-written lines. The terminal
version is `uv run python -m loosethread.play`.

打开 http://127.0.0.1:8000。第一次运行会下载 Pyodide 运行环境（约 6 MiB）。不需要 key 就能玩，此时用规则理解问题、用模板说话；
也可以填自己的 DeepSeek key，由模型理解问题、说出台词。终端版是 `uv run python -m loosethread.play`。

## Results / 结果

The evaluation study and its limits: [`docs/REPORT.md`](docs/REPORT.md). 评估研究及其局限见该报告。

## Development / 开发

```bash
uv sync --extra dev
uv run pytest
```

## License / 许可

Code: MIT (`LICENSE`). Content packs, experiment data and media: CC BY 4.0 (`LICENSE-CONTENT.md`).
