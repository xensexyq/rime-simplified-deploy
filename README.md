<a id="fcitx5-雾凇拼音术语增强部署"></a>

<div align="center">

# rime-simplified-deploy

**Fcitx5 + Rime + 雾凇拼音的中英文与工程术语增强**

[特性](#特性) · [安装](#安装) · [快速开始](#快速开始) · [恢复](#恢复) · [测试](#测试)

</div>

面向 Linux 桌面的 **Fcitx5 + Rime + 雾凇拼音（rime_ice）**，把常用中文短语、英文单词以及机器人/AI 工程术语以独立词典挂载到现有方案。

项目不会替换雾凇拼音主词库，不会清空用户目录，也不会修改用户词频数据库。雾凇已有的候选排序、自动纠错、中英混输、Emoji、拆字、标点和快捷键继续保留。

本项目不适用于 IBus、Windows 小狼毫或 macOS 鼠须管。

## 特性

- 独立补充中文短语与英文工程术语，不替换雾凇主词库。
- 增量挂载翻译器，保留用户学习数据和现有方案能力。
- 修改前备份配置，支持暂不重载、关闭英文增强及手动恢复。

## 部署原理

脚本生成四个项目专用文件：

- `xense_common_phrases.dict.yaml`
- `xense_common_phrases.schema.yaml`
- `xense_english_words.dict.yaml`
- `xense_english_words.schema.yaml`

随后只通过 `rime_ice.custom.yaml` 添加两个翻译器和方案依赖：

```text
table_translator@xense_english_words
table_translator@xense_common_phrases
```

项目不会直接修改以下雾凇文件或数据：

- `rime_ice.schema.yaml`
- `rime_ice.dict.yaml`
- `cn_dicts/`、`en_dicts/`
- `rime_ice.userdb/`
- `sync/`

已有 `rime_ice.custom.yaml` 中的翻页键、方案名称和其他补丁会被保留。内容确实需要变化时，脚本先创建带时间戳的 `.bak-*` 备份；重复执行相同部署不会持续制造备份。

首次写入会由 PyYAML 重新排版并移除原文件注释；修改前的原始文本完整保存在备份中。

## 安装

适用于 Linux 桌面的 Fcitx5；先安装雾凇拼音并确认可以正常输入。远程安装器可补齐 Debian/Ubuntu 系统依赖，但不会自动安装雾凇。其他系统请自行准备依赖。

需要检查脚本后再部署时：

```bash
git clone https://github.com/xensexyq/rime-simplified-deploy.git
cd rime-simplified-deploy
```

继续执行下方快速开始；部署会修改输入法配置，先提交或取消正在输入的内容。

## 快速开始

先确认 Fcitx5 中已经能够正常使用[雾凇拼音](https://github.com/iDvel/rime-ice)，然后在已登录图形桌面的终端中以普通用户运行：

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/xensexyq/rime-simplified-deploy/main/install.sh)
```

`install.sh` 会：

1. 检查 `fcitx5-remote`、`rime_deployer` 和 Python PyYAML；
2. 在 Debian/Ubuntu 缺少依赖时安装 `fcitx5 fcitx5-rime librime-bin python3-yaml wamerican`；
3. 确认默认用户目录中已经存在 `rime_ice.schema.yaml`；
4. 下载本项目到 `~/.local/share/rime-simplified-deploy`；
5. 增量修改 `rime_ice.custom.yaml`、重新部署并通知 Fcitx5 加载配置。

安装器不会自动下载或覆盖雾凇拼音。已有项目下载目录会先改名备份，再安装新版本。

已克隆仓库时可以直接运行：

```bash
git clone https://github.com/xensexyq/rime-simplified-deploy.git
cd rime-simplified-deploy
bash deploy.sh
```

## 项目结构

```text
install.sh     下载、检查依赖与安装入口
deploy.sh      配置补丁、词典生成及 Rime 部署
chinese/       中文补充短语
english/       英文词汇与工程别名
tests/         隔离配置及候选回归检查
```

## 文档

[参数](#参数) · [环境变量](#环境变量) · [候选策略](#候选排序策略) · [词表维护](#词表) · [验证](#部署验证) · [恢复](#恢复) · [常见问题](#常见问题)

详细操作集中在本 README，仓库名称保持兼容，不表示仍支持旧版 IBus 方案。

## 参数

| 参数 | 作用 |
| --- | --- |
| （无） | 生成补充词典、部署 Rime，并通过 `fcitx5-remote -r` 重新加载 |
| `--no-reload` | 只部署，不重新加载 Fcitx5 |
| `--set-default` | 将 `rime_ice` 放到 `default.custom.yaml` 方案列表第一位，其他方案保留 |
| `--no-english` | 停用本项目的英文补充翻译器；中文补充仍保留 |
| `-h`、`--help` | 显示帮助 |

兼容旧调用的 `--no-restart` 会按 `--no-reload` 处理。

## 环境变量

| 变量 | 默认值 |
| --- | --- |
| `RIME_USER_DIR` | `${XDG_DATA_HOME:-~/.local/share}/fcitx5/rime` |
| `RIME_SHARED_DIR` | `/usr/share/rime-data` |
| `RIME_PYTHON` | `/usr/bin/python3` |
| `RIME_ENGLISH_WORDLIST` | `/usr/share/dict/words` |
| `FCITX5_REMOTE` | `fcitx5-remote` |
| `RIME_DEPLOY_REPO` | `xensexyq/rime-simplified-deploy` |
| `RIME_DEPLOY_BRANCH` | `main` |
| `RIME_DEPLOY_HOME` | `~/.local/share/rime-simplified-deploy` |

## 候选排序策略

雾凇主拼音翻译器保持原有权重和用户学习能力。补充词典采用保守排序：

- 中文补充权重为 `1`，低于雾凇主拼音的 `1.2`；
- 英文补充权重为 `0`；
- 两个补充词典均不造句、不补全、不建立独立用户词库；
- 完整拼音仍优先给出中文，专业英文只在输入完整编码时参与候选。

这样可以补充专业词汇，同时尽量不改变已有日常输入手感。

## 词表

项目内置 147 条中文补充短语和 439 条英文词汇/别名。

中文示例：

| 输入 | 候选 |
| --- | --- |
| `meiwenti` | 没问题 |
| `huiyijiyao` | 会议纪要 |
| `dayuyanmoxing` | 大语言模型 |
| `shouyanbiaoding` | 手眼标定 |

英文及工程术语示例：

| 输入 | 候选 |
| --- | --- |
| `github` | GitHub |
| `lerobot` | LeRobot |
| `smolvla` | SmolVLA |
| `mujoco` | MuJoCo |
| `isaaclab` | IsaacLab |
| `xense` | Xense |
| `taccap` | TacCap |
| `rostwo` | ROS2 |
| `openthreed` | Open3D |
| `hdffive` | HDF5 |

英文词典还会读取系统 `/usr/share/dict/words`。系统词表缺失时继续部署，只启用仓库内置术语。运行 `--no-english` 可完全停用本项目的英文候选，不影响雾凇自带的 `melt_eng`。

自行补充：

- 中文：编辑 `chinese/phrases.tsv`，每行 `词语<Tab>连续小写拼音`；
- 英文：编辑 `english/words.txt`，每行一个词，或 `显示内容<Tab>小写字母输入码`；
- 修改后重新运行 `bash deploy.sh`。

生成到 Rime 用户目录的 `xense_*.dict.yaml` 不应直接编辑，下次部署会重新生成。

## 部署验证

部署完成后检查：

```bash
fcitx5-remote -n
```

当前输入法为 Rime 时应输出 `rime`。在文本编辑器中测试：

```text
women             → 我们应保持第一候选
shouyanbiaoding   → 候选中出现“手眼标定”
lerobot           → 候选中出现“LeRobot”
xense             → 候选中出现“Xense”
```

脚本还会自动验证已编译的 `build/rime_ice.schema.yaml` 是否包含两个补充翻译器，以及对应二进制词典是否生成。

## 手动部署

默认路径下的等价命令：

```bash
rime_dir="${XDG_DATA_HOME:-$HOME/.local/share}/fcitx5/rime"
rime_deployer --build "$rime_dir" /usr/share/rime-data "$rime_dir/build"
fcitx5-remote -r
```

重新加载前请先提交或取消正在输入的内容。

## 恢复

部署时会打印 `rime_ice.custom.yaml` 的备份路径。恢复时将占位路径替换成实际备份：

```bash
rime_dir="${XDG_DATA_HOME:-$HOME/.local/share}/fcitx5/rime"
cp -- /完整路径/rime_ice.custom.yaml.bak-时间戳 "$rime_dir/rime_ice.custom.yaml"
rime_deployer --build "$rime_dir" /usr/share/rime-data "$rime_dir/build"
fcitx5-remote -r
```

恢复旧补丁后，`xense_*` 生成文件即使仍留在用户目录也不会被主方案加载，可以稍后手工归档。不要立即重跑部署脚本，否则会再次挂载补充词典。

## 常见问题

- **找不到 `rime_ice.schema.yaml`**：先把雾凇拼音安装到 Fcitx5 用户目录并完成一次部署。
- **`rime_ice is not enabled`**：使用 `--set-default`，或把 `rime_ice` 加入 `default.custom.yaml`。
- **部署成功但候选没有变化**：执行 `fcitx5-remote -r`，切换一次输入法后再试。
- **不想引入系统大英文词表**：把 `RIME_ENGLISH_WORDLIST` 指向不存在的路径，只会使用内置术语；或者使用 `--no-english`。
- **不想影响正在运行的输入法**：使用 `--no-reload`，稍后自行重新加载。
- **部署失败**：检查脚本打印的备份路径和 `rime_deployer` 输出；脚本不会删除用户词库。

## 测试

隔离配置测试使用模拟的 `rime_deployer` 和 `fcitx5-remote`。真实候选测试会把本机雾凇目录复制到临时目录，并排除 `userdb`、`sync` 和备份文件；不会修改真实输入法配置。

```bash
/usr/bin/python3 -B -m unittest discover -s tests -v
```

没有安装雾凇或 librime 时，真实候选测试会跳过。可以用 `RIME_ICE_TEST_DIR` 指向其他雾凇配置源目录。

## 致谢与许可

### 致谢与参考项目

- [雾凇拼音（rime-ice）](https://github.com/iDvel/rime-ice)：本项目补充词典所挂载的输入方案，保留原方案及词库。
- Fcitx5 / Rime：提供输入法运行与词典部署能力；本项目通过其命令行工具部署和重载，不替代输入法本体。
- PyYAML 与系统英文词表：分别用于配置处理和英文词汇补充；本项目内置术语与外部词表的来源、授权分别保留。

### 许可证

[MIT](LICENSE)。内置中英文词表由项目维护；雾凇拼音及系统英文词表遵循各自许可证。
