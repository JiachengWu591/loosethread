# Parser on the frozen test set (P2)

Computed from `results/rows/` by `python -m loosethread.verify`.

```text
DeepSeek (guarded): accuracy 138/148 = 93.2% [Wilson 95%: 88.0%, 96.3%]; strict 138/148; charged_wrong 3; needless_rephrase 7; invalid 0
  zh: accuracy 85/88 = 96.6% [Wilson 95%: 90.5%, 98.8%]; strict 85/88; charged_wrong 1; needless_rephrase 2; invalid 0
  en: accuracy 53/60 = 88.3% [Wilson 95%: 77.8%, 94.2%]; strict 53/60; charged_wrong 2; needless_rephrase 5; invalid 0
DeepSeek (raw): accuracy 143/148 = 96.6% [Wilson 95%: 92.3%, 98.5%]; strict 143/148; charged_wrong 3; needless_rephrase 2; invalid 0
  zh: accuracy 86/88 = 97.7% [Wilson 95%: 92.1%, 99.4%]; strict 86/88; charged_wrong 1; needless_rephrase 1; invalid 0
  en: accuracy 57/60 = 95.0% [Wilson 95%: 86.3%, 98.3%]; strict 57/60; charged_wrong 2; needless_rephrase 1; invalid 0
  guard vs raw: only guarded right 0, only raw right 5; exact McNemar p = 0.0625
  usage: 333546 tokens, 201.5 s, at most CNY 0.6790 (0.00459 per question)
Rules: accuracy 132/148 = 89.2% [Wilson 95%: 83.2%, 93.2%]; strict 130/148; charged_wrong 8; needless_rephrase 8; invalid 0
  zh: accuracy 81/88 = 92.0% [Wilson 95%: 84.5%, 96.1%]; strict 79/88; charged_wrong 4; needless_rephrase 3; invalid 0
  en: accuracy 51/60 = 85.0% [Wilson 95%: 73.9%, 91.9%]; strict 51/60; charged_wrong 4; needless_rephrase 5; invalid 0
  usage: 0 tokens, 0.0 s, at most CNY 0.0000 (0.00000 per question)
Local Qwen (guarded): accuracy 114/148 = 77.0% [Wilson 95%: 69.6%, 83.1%]; strict 109/148; charged_wrong 16; needless_rephrase 14; invalid 4
  zh: accuracy 73/88 = 83.0% [Wilson 95%: 73.8%, 89.4%]; strict 72/88; charged_wrong 11; needless_rephrase 4; invalid 0
  en: accuracy 41/60 = 68.3% [Wilson 95%: 55.8%, 78.7%]; strict 37/60; charged_wrong 5; needless_rephrase 10; invalid 4
Local Qwen (raw): accuracy 111/148 = 75.0% [Wilson 95%: 67.5%, 81.3%]; strict 106/148; charged_wrong 25; needless_rephrase 8; invalid 4
  zh: accuracy 68/88 = 77.3% [Wilson 95%: 67.5%, 84.8%]; strict 67/88; charged_wrong 19; needless_rephrase 1; invalid 0
  en: accuracy 43/60 = 71.7% [Wilson 95%: 59.2%, 81.5%]; strict 39/60; charged_wrong 6; needless_rephrase 7; invalid 4
  guard vs raw: only guarded right 5, only raw right 2; exact McNemar p = 0.453
  usage: 334035 tokens, 71.8 s, at most CNY 0.0000 (0.00000 per question)
DeepSeek vs rules: 148 shared items: only first right 10, only second right 4; exact McNemar p = 0.18
```
