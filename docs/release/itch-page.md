# itch.io page copy

Everything here can be pasted as it stands. It makes no claim about other games (`docs/RELATED_WORK.md`, CLAUDE.md).

## Fields

- **Title**: 破绽 / Loose Thread. Use both names: several itch.io projects are called Loose Thread or Loose Threads, two of them detective games (D-050).
- **Short description**: 用自己的话审问嫌疑人，找出证词的破绽。Question suspects in your own words, and find the loose thread.
- **Classification**: Games. **Kind of project**: HTML. **Release status**: Released. **Pricing**: Free, or no payments.
- **Genre**: Puzzle. **Tags**: detective, mystery, deduction, puzzle, text-based, daily, chinese, llm, singleplayer. Choose what the form accepts.
- **Languages**: Chinese (Simplified), English. **Inputs**: Keyboard, Touch. **Accessibility**: leave blank unless you have checked it.
- **Screenshots**, from `assets/screenshots/`: `contradiction-zh.png`, `contradiction-en.png`, `accusation-en.png`, `ending-en.png`. The ending shows the truth of a past case, 20261014. **Cover**: `itch-cover.png`, 630 × 500.

## AI disclosure

itch.io asks whether a project uses generative AI. An honest answer, which is yours to give:

- **Code and text**: written with an AI coding assistant (Claude).
- **In play**: with a player's own key, a model (DeepSeek) reads questions and writes lines at run time. With no key, nothing is generated.
- **Graphics and audio**: none are generated. The screenshots are of the game itself.

## Description

破绽 · 中文

一件东西被偷了，所有人都走不了。你是碰巧在场的退休侦探，能问的问题有限。

用自己的话问嫌疑人：“九点三刻你在哪？”“跟谁在一起？”每个人的回答都会自动记进笔记。无辜的人在作案时间窗里不说谎，犯人会说。找到两条不能同时成立的记录，指认犯人，揭穿谎言。

- 每天一个新案子（按你的本地日期），由程序生成，求解器验证唯一可解。
- 三个场景，四种谎言，中英文随时切换。
- 想要更难，可以开困难模式：不提示矛盾，自己对照笔记和地图。
- 打完有一张不含答案的分享卡。

**不用 key 就能玩。** 这时问题由规则理解，台词是模板，有点像填表，什么也不会离开你的设备。想让模型来理解问题、说台词，可以填自己的 DeepSeek key：问题会发给 DeepSeek，费用从你的 key 扣（我们测试时每局不到 ¥0.1）。模型只拿到这一问允许说的事实，拿不到真相。

**这也是一个研究项目。** 我们测了这种分层做法到底有没有用，结论好坏都写了：违规确实更少，但差距没有看上去那么大；防泄露没有得到证明；耗时约为两倍。[评估报告](https://github.com/JiachengWu591/loosethread/blob/main/docs/REPORT.md) · [源码](https://github.com/JiachengWu591/loosethread) · [隐私说明](https://github.com/JiachengWu591/loosethread/blob/main/docs/PRIVACY.md)

Loose Thread · English

Something has been stolen, and nobody can leave. You are a retired detective who happens to be there, with only so many questions.

Ask in your own words: "Where were you at quarter to ten?" "Who was with you?" Every answer goes into your notebook by itself. Innocent people do not lie about the theft window, and the culprit does. Find two records that cannot both be true, name the culprit, and expose the lie.

- A new case each day, by your own local date, generated and checked by a solver to have exactly one solution.
- Three settings, four shapes of lie, and Chinese or English at any time.
- For more challenge, hard mode turns off the contradiction hints, leaving you the notebook and the map.
- A share card with no answer in it at the end.

**It plays with no key.** Rules read your questions and the lines are templates, somewhat like filling in a form, and nothing leaves your device. To let a model read your questions and speak the lines, add a DeepSeek key of your own: your questions go to DeepSeek, and your key pays, under ¥0.1 a game in our tests. The model receives only the facts each answer may state, and never the truth.

**It is also a research project.** We measured whether these layers help, and reported what failed: fewer flagged failures, by less than it first looks; no shown resistance to leaking; about twice the time. [The evaluation](https://github.com/JiachengWu591/loosethread/blob/main/docs/REPORT.md) · [Source](https://github.com/JiachengWu591/loosethread) · [Privacy](https://github.com/JiachengWu591/loosethread/blob/main/docs/PRIVACY.md)

All cases, people and places are fictional. Code MIT, content CC BY 4.0.
