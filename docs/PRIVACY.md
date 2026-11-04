# Privacy / 隐私说明

**In short**: with no key, nothing you type leaves your device. With your own key, your questions go to DeepSeek. This project runs no
server and no analytics, and sets no cookies.

**简而言之**：不填 key 时，你输入的内容不会离开你的设备。填了自己的 key，你的问题会发给 DeepSeek。本项目没有服务器，不做统计，也不设
cookie。

## With no key / 不填 key

The whole game runs in your browser. Your questions and the answers stay on your device.

The host that serves the page (GitHub Pages, itch.io, or your own machine) sees ordinary web requests, under its own policy. itch.io's page
around the game has its own cookies and analytics, which this project does not control.

整个游戏在你的浏览器里运行，问题和回答都留在你的设备上。提供页面的网站（GitHub Pages、itch.io 或你自己的电脑）能看到普通的网页请求，
按它们自己的政策处理。itch.io 外层页面有自己的 cookie 和统计，本项目无法控制。

## What your browser keeps / 浏览器里存了什么

In `localStorage`, on this device: your progress in each case (the questions you typed and the answers), your language, and whether hard
mode is on. The last 14 games are kept. It holds neither the case's truth nor your key. Clearing the site's data removes it.

A host that serves many games from one web address may let those other games read this storage. Do not type anything personal into a
question.

存在这台设备的 `localStorage` 里：每个案子的进度（你输入的问题和回答）、语言、是否开启困难模式。只保留最近 14 局。这里面没有案件真相，也
没有你的 key。清除网站数据就会删除。如果一个网站用同一个网址提供很多游戏，那些游戏可能读得到这些内容，所以不要在问题里输入个人信息。

## With your own key / 填自己的 key

Your browser calls `api.deepseek.com` directly. This project is not in between. DeepSeek charges your key, and handles what it receives under
its own terms and privacy policy.

- **Sent for each question**: what you typed, the names of the case's people, places and item, the evening's times, and a few worked examples.
- **Sent for each reply**: the speaker's public card, the question as the game understood it, the facts this answer may state, and a tone.
- **Never sent**: who did it, or where anyone really was. The model does not receive these, because the game does not put them in any
  request. A suspect's lie is sent as the fact they may state.
- **Your key**: sent only to DeepSeek, in the request's `Authorization` header. It stays in the memory of the page's worker, and is never
  written to storage. A refresh or closing the page drops it.

A key typed into any web page can be read by that page and by your browser's extensions. Prefer a key with a spending limit, and delete it
when you are done.

你的浏览器直接请求 `api.deepseek.com`，本项目不经手。费用从你的 key 扣，DeepSeek 按它自己的条款和隐私政策处理收到的内容。

- **每次提问发送**：你输入的内容，案件里的人名、地名、物品名，当晚的时间范围，以及几个示例。
- **每次回答发送**：说话人的公开资料、游戏理解到的问题、这一问允许说的事实，以及语气。
- **绝不发送**：谁是犯人、每个人实际在哪。游戏不会把这些放进任何请求，所以模型拿不到。嫌疑人的谎话是作为“允许说的事实”发送的。
- **你的 key**：只发给 DeepSeek，放在请求的 `Authorization` 头里。它只留在页面 worker 的内存中，不写入存储，刷新或关闭页面后就没了。

任何填进网页的 key，都可能被该网页和浏览器扩展读到。建议使用有额度限制的 key，用完删除。

## The terminal version / 终端版

It reads a key from the environment variable `DEEPSEEK_API_KEY`, and sends the same content. With no backend chosen, nothing leaves your machine.

它从环境变量 `DEEPSEEK_API_KEY` 读取 key，发送的内容相同。不指定模型后端时，什么都不会离开你的电脑。

## The study's data / 研究数据

`results/rows/` holds scripted runs only, and no player's data.

`results/rows/` 里只有脚本运行的数据，没有任何玩家数据。
