# IBus Rime 简体中文一键部署

在 Linux 桌面（**IBus + Rime**）上一键配置“朙月拼音·简化字”方案 `luna_pinyin_simp`：

- **稳定输出简体中文**：修复“简体方案却出繁体”的问题。
- **英文单词候选**：不切换中英文就能直接打出 `hello`、`GitHub`、`JSON` 等常用英文。

不适用于 Fcitx、Windows 小狼毫或 macOS 鼠须管。

## 快速开始

在已登录图形桌面的终端中以**普通用户**运行（不要 sudo）：

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/xensexyq/rime-simplified-deploy/main/install.sh) --set-default
```

`install.sh` 会：

1. 检查依赖；缺少时在 Debian/Ubuntu 上通过 `apt` 安装 `ibus ibus-rime librime-bin rime-data-luna-pinyin python3-yaml wamerican`（会请求 sudo）。其他发行版请先用系统包管理器手动安装对应软件包。
2. 下载本仓库到 `~/.local/share/rime-simplified-deploy`。
3. 执行 `deploy.sh`，参数原样传入。

已克隆仓库时也可以直接运行：

```bash
git clone https://github.com/xensexyq/rime-simplified-deploy.git
cd rime-simplified-deploy
bash deploy.sh --set-default
```

> 新装 IBus Rime 时，还需要在系统设置的“键盘 / 输入源”中添加“中文（Rime）”。脚本只会启用 Rime 引擎，不会修改桌面的输入源列表或系统界面语言。

## 参数

| 参数 | 作用 |
| --- | --- |
| （无） | 修改配置、重新部署、重启 IBus 并确认 Rime 已运行 |
| `--no-restart` | 只部署配置，不重启 IBus；之后自行执行 `ibus restart` |
| `--set-default` | 将 `luna_pinyin_simp` 放到 `default.custom.yaml` 中 `schema_list` 的第一位（其余方案保留），切换后默认使用该方案 |
| `--no-english` | 不提供英文单词候选；若之前已启用，会移除相关配置 |
| `-h`, `--help` | 显示帮助 |

| 环境变量 | 默认值 |
| --- | --- |
| `RIME_USER_DIR` | `${XDG_CONFIG_HOME:-~/.config}/ibus/rime` |
| `RIME_SHARED_DIR` | `/usr/share/rime-data` |
| `RIME_PYTHON` | `/usr/bin/python3`（需要已安装 PyYAML） |
| `RIME_ENGLISH_WORDLIST` | `/usr/share/dict/words`（系统英文词表，由 `wamerican` 等软件包提供） |

## 问题与配置原理

常见故障是自定义配置把 `simplifier/option_name` 设为空字符串，或移除了简体转换开关：方案名叫“简体”，实际却输出繁体。

本脚本为简体转换指定独立开关 `simplified_output`，默认开启，并明确使用 OpenCC 的 `t2s.json` 繁转简规则。使用独立开关可以避免原有 `zh_simp`（简繁切换快捷键）把转换关掉。

配置文件：`~/.config/ibus/rime/luna_pinyin_simp.custom.yaml`。以下仅为相关片段，**不要用它覆盖完整文件或原有 switches 列表**：

```yaml
patch:
  switches:
    # 保留原来的中英文、全半角和标点开关，在列表中追加：
    - name: simplified_output
      reset: 1
  simplifier/option_name: simplified_output
  simplifier/opencc_config: t2s.json
```

## 英文单词候选

默认方案只有拼音词典，输入 `hello` 只会得到“合理咯”之类的拼音拆分结果，常用英文必须先按 Shift 切换到英文模式。脚本默认为方案增加一个英文词典翻译器 `table_translator@english_words`：

| 输入 | 第一候选 | 说明 |
| --- | --- | --- |
| `hello` / `thanks` / `email` | hello / thanks / email | 不是完整拼音，英文排第一 |
| `github` / `json` / `wifi` / `chatgpt` | GitHub / JSON / WiFi / ChatGPT | 内置词表指定了大小写 |
| `women` / `make` / `change` | 我们 / 马克 / 嫦娥 | 同时是完整拼音时中文优先，英文在后面的候选中 |
| `nihao` / `zhongwen` | 你好 / 中文 | 拼音输入不受影响 |

词典由两部分生成为用户目录下的 `english_words.dict.yaml`，每次运行脚本都会重新生成：

- [`english/words.txt`](english/words.txt)：内置的常用技术词汇、品牌名和网络用语，并指定大小写（如 `GitHub`、`macOS`、`Node.js` 的输入码为 `nodejs`）。可以按“每行一个词”自行添加后重新运行脚本。
- 系统英文词表 `/usr/share/dict/words`（Debian/Ubuntu 的 `wamerican`，约 7 万个词）。同一输入码只保留一个词，优先小写形式；不存在时只启用内置词表并给出提示。

只匹配完整输入的单词，不做前缀补全，避免拼音输入时出现大量无关英文；英文的 `initial_quality` 为 `0`，因此完整拼音仍然中文优先。需要输入大写开头的英文时，直接按住 Shift 输入首字母即可进入英文直通。

## 脚本行为

- 检查 `rime_deployer`、`ibus`、PyYAML 和 `luna_pinyin_simp` 方案文件。
- 若尚未部署过 Rime（没有 `build/default.yaml`），先执行一次初始部署。
- 检查 `luna_pinyin_simp` 已启用；未启用时报错退出，或使用 `--set-default` 自动启用。
- 已有 `luna_pinyin_simp.custom.yaml` 时：保留其他配置项与原有开关，只更新简体转换规则和默认开关，修改前创建带时间戳的 `.bak-*` 备份。
- 没有该文件时：以方案自带的开关为基础新建，并去掉被取代的 `zh_simp` 开关。
- 默认启用英文候选：生成 `english_words.dict.yaml` 与 `english_words.schema.yaml`，在自定义配置中追加英文翻译器和方案依赖（保留原有翻译器与依赖）。
- 所有校验在写入前完成；校验失败时不修改任何文件。
- 重新部署，并检查生成的 `build/luna_pinyin_simp.schema.yaml` 包含预期配置、英文词典已编译。
- 重启 IBus，最多重试 15 秒启用 Rime 并确认引擎名称。

重复执行结果不变（不会重复添加开关）；每次都会备份执行前的配置。YAML 重新写入时会改变排版并移除注释，原始文本保存在备份中。

运行前请提交或取消正在输入的拼音，重启输入法可能中断未提交的输入。

## 验收

```bash
ibus engine
```

应输出 `rime`。若启用了多个 Rime 方案，请在方案菜单（默认 `` Ctrl+` `` 或 `F4`）中选择“拼音（简体）”/“朙月拼音·简化字”。在文本编辑器中输入：

| 拼音 | 预期简体 | 不应出现的繁体形式 |
| --- | --- | --- |
| `zhong wen shu ru fa` | 中文输入法 | 中文輸入法 |
| `jian ti` | 简体 | 簡體 |
| `han zi` | 汉字 | 漢字 |

脚本验证的是部署结果和引擎状态，实际输入仍需上述人工验收。

## 手动部署命令

```bash
rime_dir="${XDG_CONFIG_HOME:-$HOME/.config}/ibus/rime"
rime_deployer --build "$rime_dir" /usr/share/rime-data "$rime_dir/build"
ibus restart
```

IBus 重启是异步的。如果刚重启时提示 `No engine is set`，等待几秒后执行 `ibus engine rime`，再执行 `ibus engine` 检查。

## 恢复原配置

脚本会打印备份的完整路径。将下面占位路径替换成需要恢复的备份：

```bash
rime_dir="${XDG_CONFIG_HOME:-$HOME/.config}/ibus/rime"
cp -- /完整路径/luna_pinyin_simp.custom.yaml.bak-时间戳 \
  "$rime_dir/luna_pinyin_simp.custom.yaml"
rime_deployer --build "$rime_dir" /usr/share/rime-data "$rime_dir/build"
ibus restart
```

`default.custom.yaml` 的备份（使用 `--set-default` 时产生）同理。若配置文件是脚本新建的（没有备份），删除该文件后重新部署即可恢复默认。恢复后不要立即重跑部署脚本，否则会再次应用简体设置。备份只覆盖上述自定义配置，不是 Rime 用户词库的备份。

## 常见问题

- **`luna_pinyin_simp is not enabled`**：使用 `--set-default` 运行，或在 `default.custom.yaml` 的 `schema_list` 中加入该方案。
- **缺少方案文件**：安装朙月拼音方案数据（Debian/Ubuntu：`rime-data-luna-pinyin`）。
- **部署失败**：脚本停止并保留备份；检查 `rime_deployer` 错误输出，必要时按上节恢复。
- **引擎启动检查失败**：在已登录图形桌面的用户终端运行；等待服务启动后再执行 `ibus engine rime`。不要从 root 或没有桌面会话的 SSH 环境重启。
- **英文候选没有出现**：确认运行时没有加 `--no-english`，并已重启 IBus；检查 `build/english_words.table.bin` 是否存在。要输入的词不在词表中时，加到 `english/words.txt` 后重新运行脚本。
- **不想要英文候选**：运行 `bash deploy.sh --no-english`。
- **仍输出繁体**：确认当前为目标 Rime 方案，并已重新加载输入法；检查 `build/luna_pinyin_simp.schema.yaml` 中的 `simplifier` 与 `switches`。不要直接修改 `build` 目录下的文件，后续部署会覆盖它们。

## 测试

测试使用临时目录和模拟的 `rime_deployer` / `ibus`，不会改动真实配置或重启输入法：

```bash
/usr/bin/python3 -m unittest discover -s tests -v
```

已在 Ubuntu 24.04（ibus-rime 1.5.0、librime 1.10）上用真实 `rime_deployer` 对已有配置和空白配置目录验证；上文英文候选表格中的排序结果通过 librime 模拟按键得到。

## 许可证

[MIT](LICENSE)。运行时读取的系统英文词表不随本仓库分发，遵循其所属软件包的许可。
