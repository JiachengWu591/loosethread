# 破绽 / Loose Thread v0.1.0

一款中英双语的推理游戏：用自己的话审问嫌疑人，从证词的破绽里找出犯人。每个案件由程序生成，并由求解器验证唯一可解。
A bilingual deduction game: question suspects in your own words, and find the culprit through the loose threads in their testimony.
Every case is generated, and checked by a solver to have exactly one solution.

**▶ [在浏览器里玩 / Play in your browser](https://jiachengwu591.github.io/loosethread/)**: nothing to install, no key. 不用安装，不用 key。

## 这个版本有什么 / What is in it

- 每天一个新案子（按你的本地日期），三个场景，四种谎言。A new case each day, by your own local date, in three settings, with four shapes of lie.
- 自动笔记和矛盾提示，也可以开困难模式关掉提示。A notebook that fills itself in, with hints, or a hard mode without them.
- 不含答案的分享卡。A share card with no answer in it.
- 不填 key 时用规则和模板，什么都不外发；填自己的 DeepSeek key 后由模型理解问题、说台词。With no key, rules and templates, and nothing leaves your device. With a DeepSeek key of your own, a model reads the questions and speaks the lines.
- 一份可复现的评估，可离线重算全部表格。A reproducible evaluation, with every table recomputable offline.

## 评估说了什么 / What the evaluation says

The layered NPC had fewer flagged failures than a prompt-only one, 0/204 against 60/204, by less than that suggests. **Resistance to leaking was not shown**: a hardened prompt and the layers both leaked 0 of 200 times, while an unhardened prompt leaked 19 of 200. The layers cost about twice the time. See [`docs/REPORT.md`](docs/REPORT.md) for the design and its limits.

分层 NPC 的违规少于只靠提示词的版本（0/204 对 60/204），但差距没有看上去那么大。**防泄露没有得到证明**：加固提示词和分层版在 200 次攻击中都是 0 次泄露，没有加固的提示词是 19 次。分层的耗时约为两倍。设计和局限见报告。

## 已知局限 / Known limits

- 没有 key 的玩家接触不到模型，台词是模板。With no key you never meet a model, and the lines are templates.
- 约一半的案子里，同一个人两句话的矛盾提示会直接指向犯人。In about half of cases, a hint on one person's own two answers names the culprit.
- 不同时区的人可能在玩不同的案子，可以对一下案件号。People in different time zones can be on different cases: compare the case number.
- 发布前没有陌生玩家玩过。No stranger had played it before this release.

## 文件 / Files

`loosethread-web.zip` is the static site, for hosting yourself. It holds third-party software under its own licenses: see `NOTICES.txt` inside. Privacy: [`docs/PRIVACY.md`](docs/PRIVACY.md). Full list of changes: [`CHANGELOG.md`](CHANGELOG.md).

`loosethread-web.zip` 是静态站点，可以自己托管，其中的第三方软件各有许可，见里面的 `NOTICES.txt`。
