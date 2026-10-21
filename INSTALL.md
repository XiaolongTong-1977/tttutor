# tttutor 安装与使用说明

Typing Tutor IV 的现代终端复刻版 —— 纯 Python 3 标准库实现，
在普通终端（curses）中运行，无需 DOSBox / xterm。

---

## 1. 环境要求

| 项目 | 要求 |
|------|------|
| Python | **3.10 或更高**（开发验证过 3.12 / 3.13） |
| 操作系统 | Linux、macOS、Windows（WSL 或原生） |
| 终端 | 任意支持 curses 的终端，建议 ≥ 80×25 |
| 第三方依赖 | **无**（纯标准库） |

> Linux / macOS 的 Python 自带 `curses`；
> Windows 原生 Python 需要 `windows-curses`（`requirements.txt`
> 已带环境标记，pip 在 Windows 上会自动装上，其他平台自动跳过）。

---

## 2. 安装

### 方式一：pip 安装（推荐）

```bash
cd tttutor-port
python -m pip install -r requirements.txt   # Windows 上装 windows-curses；其他平台无操作
python -m pip install .
```

安装后会得到 `tttutor` 命令，直接运行：

```bash
tttutor
```

### 方式二：免安装直接运行

不安装也可以，源码自带启动器：

```bash
cd tttutor-port
python start.py
```

> 两种方式完全等价。启动器会把程序目录自动加入 `sys.path`，
> 不需要预先 `pip install -e .`。

### conda 环境示例

```bash
conda activate spark13
python start.py --check        # 先检查环境
python start.py                # 启动
```

---

## 3. 启动命令参数

```bash
python start.py [选项]
```

| 选项 | 说明 |
|------|------|
| `--history PATH` | 指定历史记录文件（默认 `~/.tttutor/history.jsonl`） |
| `--tst-dir DIR` | 额外加载指定目录下的 `.TST` 课文文件 |
| `--instructor [PASSWORD]` | 以教师模式启动（默认密码 `KRIYA`，可省略以交互输入） |
| `--check` | 环境自检后退出（无需 TTY） |
| `--init` | 创建配置目录后退出 |
| `--reset [--yes]` | 清空历史 / 设置 / 高分（`--yes` 跳过确认） |
| `--version` | 打印版本信息后退出 |

安装为 pip 包后，`tttutor` 命令支持 `--history / --tst-dir`。

---

## 4. 首次使用流程

1. 启动后按 `Enter` 进入欢迎页，再按 `Esc` 跳过介绍；
2. `Please type your name..` —— 输入姓名回车（**不能为空**）；
3. 确认当天日期 → 选择速度目标 → 每周练习目标 → 技能水平；
4. `Where would you like to begin..` —— 选 `Main Menu` 进入主菜单：
   `Lessons  Tests  Reports  Options  Game  Help  Quit`；
5. 菜单操作为原版方式：`←`/`→` 或空格移动高亮，`Enter` 选择，
   也可直接按菜单项首字母选中，`Esc` 返回上级。

个人信息与进度保存在 `~/.tttutor/`：
`history.jsonl`（练习历史）、`settings.json`（目标/设置/教师密码）、
`fzvf.json`（游戏高分榜）。

---

## 5. 教师（Instructor）模式

```bash
python start.py --instructor KRIYA
```

进入后可使用：Encrypt（加密 .TST 测试文件）、Reports（学生成绩 /
Composite 汇总 / 单个学生 Progress·Speed·Accuracy）、
Password（修改教师密码）、Delete（删除学生记录）。

> 默认密码 `KRIYA`（与原版一致），可在教师模式中修改，
> 密码保存在 `settings.json`。

---

## 6. 运行测试

源码包内置 189 个测试（单元 + 集成驱动），任意环境执行：

```bash
cd tttutor-port
PYTHONPATH=. python -m unittest discover -s tests
```

---

## 7. 常见问题

**Q: 没有声音？**
程序按 ALSA → PulseAudio → macOS afplay → Windows beep → 终端响铃
的顺序自动选择。无声一般是播放器缺失，属正常现象，不影响功能。

**Q: 界面错位？**
界面按原版 80×25 设计，终端 ≥ 80 列 × 25 行效果最佳；
更小的终端会自动截断适配，不会崩溃。

**Q: Windows 上 `No module named '_curses'`？**
```bash
python -m pip install -r requirements.txt   # 安装 windows-curses
```
或者改用 WSL。

**Q: 如何彻底重置？**
```bash
python start.py --reset --yes
```

---

## 8. 卸载

```bash
python -m pip uninstall tttutor
rm -rf ~/.tttutor        # 如需清除个人数据
```

---

## 9. 目录结构

```
tttutor-port/
├── start.py                 # 总启动器（免安装直接运行）
├── requirements.txt         # 运行时依赖（仅 Windows 需要 windows-curses）
├── pyproject.toml           # pip 安装配置
├── INSTALL.md               # 本文档
├── tttutor/                 # 程序包
│   ├── ui.py                # 界面（TT.EXE 原版 80x25 布局）
│   ├── engine.py            # 打字引擎
│   ├── invaders.py          # Letter Invaders 引擎
│   ├── original_text.py     # 原版文本流渲染器
│   ├── content.py           # 课程/键盘区内容
│   ├── history.py           # 历史记录
│   ├── settings.py          # 设置持久化
│   ├── sound.py             # 音效
│   └── data/                # 原版词库/文本流提取数据 + .TST 文件
├── tools/                   # 原版数据提取工具
└── tests/                   # 测试
```
