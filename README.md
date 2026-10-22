# tttutor

现代终端打字练习软件 —— 纯 Python 实现，仅依赖标准库。

*[English README](README.en.md)*

## 项目缘起
功能上复刻经典的 16 位 DOS 打字教学软件——Kriya Systems 公司于 1987 年推出
的著名作品 `Typing Tutor IV`。tttutor 用现代 Python 技术栈重新实现了同样的
*功能理念*——顺序课程、逐字符准确率跟踪、WPM（每分钟单词数）计算、历史记录
持久化、"字母入侵者"（Letter Invaders）小游戏——而不再需要 DOSBox 和 16 位
实模式代码：

| TT IV 的概念                     | tttutor 的实现                              |
|----------------------------------|---------------------------------------------|
| 菜单（课程/测验/报表/…）         | `App.menu_screen`，curses 高亮横排菜单      |
| 带逐字符反馈的练习行             | `TypingDrill` + `progress_chars`            |
| 个人档案与历史（TT.HIS 文件）    | `history.py` —— `~/.tttutor/` 下的 JSONL    |
| 字母入侵者游戏                   | `invaders.py` —— 单词式回合、Boomlet、      |
|                                  | Word Ship、双人模式、护盾                   |
| WPM/准确率报表界面               | 逐键速度/准确率图表                         |
| 教师（Instructor）模式           | `--instructor`，密码、加密、删除、综合报表  |

本项目未复用 TT IV 的任何源代码，而是基于公开文档记录的功能集进行的*全新
实现*。`.TST` 课程文件（纯文本格式）可通过 `--tst-dir` 直接加载。

## 使用说明书
见 [MANUAL.md](MANUAL.md)（功能详解、游戏规则、教师模式、故障排除）。

## 安装
见 [INSTALL.md](INSTALL.md)。运行时零第三方依赖（纯标准库），
`requirements.txt` 仅在 Windows 原生环境需要 `windows-curses`：

```
pip install -r requirements.txt
pip install .        # 得到 tttutor 命令；或免安装直接 python start.py
```

## 运行
```
python start.py                         # 默认文本界面
python start.py --history ./history.jsonl
python start.py --tst-dir ./lessons
python start.py --instructor KRIYA      # 教师模式
python start.py --check                 # 环境诊断
```

`start.py` 完全自包含（仅标准库），在 conda `spark13` 环境与系统 Python 下
均可运行。

## 原版压缩词库
1987 年的 EXE 将其词库以位压缩流的形式存储在 `DS:0x214e` /
`DS:0x2992`（46 条课程流 × 23 个桶）。已按位精确提取：

```
python tools/extract_word_corpus.py /mnt/qdata1/tt/game/extracted/TT.EXE
```

输出：

* `tttutor/data/tt_word_corpus.json` —— 每条目含所属流/桶及其原始 5 位
  字母编码。
* `tttutor/data/tt_word_corpus.txt` —— 每行一个去重后的单词。

当前提取结果：**4019 条目 / 3876 个去重单词 / 0 解码错误**。
游戏的"练习键位"模式按学生已学键位过滤此词库；"全键盘"模式使用整个词库。
单词长度限制为 14 个字符，与 TT.EXE 的 15 字节单词缓冲区一致。实测见过的
原版单词如 `sad`、`laf`、`fla`、`camp`、`kate`、`jessie`、`street`、
`can` 均存在于提取结果中。

## 原版课文/文本流
EXE 还含有 51 条 token/宏流，位于 `DS:0x8632` / `DS:0x8698`，由
`FUN_1000_64cc` 展开，包含：

* 字面量与宏调用；
* 以上述词库为后盾的单词 token；
* 44 个内容生成器（姓名、地址、电话、日期、社保号、金额、算术、标点等）。

`tools/extract_text_streams.py` 将精确的流结构导出至
`tttutor/data/tt_text_streams.json`。`tttutor/original_text.py` 是该渲染器
的 Python 移植版，用于：

* 原版 Practice 练习（按已学键位过滤的单词）；
* 游戏的单词来源（模板单词 + 词库池）。

流结构与词库单词均为位精确复刻。内容生成器（姓名/地址/号码）移植自反编译
例程，但每次渲染取新的随机值，与原版行为一致。

## TT.EXE 风格渲染
curses 界面遵循原版 80x25 布局：

* 第 0 行：屏幕标题（左）与用户名（右）
* 第 1 行：整行虚线分隔
* 第 2 行：横排菜单条（`Lessons  Tests  Reports  Options  Game  Help  Quit`）
* 第 3 行：高亮菜单项的子菜单/说明
* 第 4 行起：绿色 CP437 单线框，用于帮助与对话框内容
* 末行：`Esc -> ...` 父级提示

导航使用左右方向键或空格键；Enter 确认；直接按首字母即可选中，与 TT.EXE
的菜单行为完全一致。对话框将选项置于嵌套绿色框内，选中条为黄字洋红底。
练习界面使用原版三框布局：带 `^`/`v` 指针的练习行、"当前焦点键"框、
速度/准确率框。游戏保留原版的 `Round / Score / user` 头部、18 行战场、
护盾行与底部 `Esc -> ...` 行。

## 代码结构
```
tttutor/
  engine.py     —— 打字状态与统计（不依赖 UI）
  content.py    —— 内置课程
  lessons.py    —— 内置课程 + .TST 磁盘课程的注册表
  history.py    —— JSONL 会话持久化
  invaders.py   —— 忠实复刻的 Letter Invaders 状态机
  settings.py   —— 持久化的目标、练习数、密码、已学键位
  ui.py         —— curses 界面（菜单、课程、测验、报表、游戏、帮助）
  cli.py        —— 共享 CLI（--check/--init/--reset/--version 等）
  __main__.py   —— `python -m tttutor` 入口（委托至 cli.py）
```

## 跨平台
整个程序可在任何支持 curses 的终端中运行：
- Linux、BSD                —— 原生支持
- macOS                      —— 原生支持
- Windows                    —— 通过 WSL，或任何自带 libncurses 的现代终端
  （Windows Terminal + WSL、ConEmu + cygwin 等）

无原生扩展、无 PyPI 依赖、无平台相关代码。

## 鸣谢 / Acknowledgments
tttutor is a modern terminal remake of the classic DOS typing tutor **Typing
Tutor IV** (© 1987 Kriya Systems), faithfully reimplemented in Python. The
reverse engineering, feature cloning, code refactoring and documentation were
assisted by the **DeepSeek V4.1 Flash** large language model — special thanks!
