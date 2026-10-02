#!/usr/bin/env bash
# 一键部署（Linux 桌面，IBus）：
#   bash <(curl -fsSL https://raw.githubusercontent.com/xensexyq/rime-simplified-deploy/main/install.sh)
# 额外参数会原样传给 deploy.sh，例如：
#   bash <(curl -fsSL .../install.sh) --set-default
set -euo pipefail

REPO="${RIME_DEPLOY_REPO:-xensexyq/rime-simplified-deploy}"
BRANCH="${RIME_DEPLOY_BRANCH:-main}"
DEST="${RIME_DEPLOY_HOME:-$HOME/.local/share/rime-simplified-deploy}"

say() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m错误：\033[0m%s\n' "$*" >&2; exit 1; }

[[ $EUID -ne 0 ]] || die '请以当前桌面用户运行，不要使用 sudo/root。'
command -v curl >/dev/null || die '请先安装 curl。'
command -v tar >/dev/null || die '请先安装 tar。'

deps_ok() {
  command -v ibus >/dev/null && command -v rime_deployer >/dev/null \
    && [[ -f "${RIME_SHARED_DIR:-/usr/share/rime-data}/luna_pinyin_simp.schema.yaml" ]] \
    && "${RIME_PYTHON:-/usr/bin/python3}" -c 'import yaml' 2>/dev/null
}

if ! deps_ok; then
  if command -v apt-get >/dev/null; then
    say '安装 IBus Rime 及依赖（需要 sudo）'
    sudo apt-get update
    sudo apt-get install -y ibus ibus-rime librime-bin rime-data-luna-pinyin python3-yaml wamerican
  else
    die '缺少依赖。请用系统包管理器安装 ibus、ibus-rime、rime_deployer（librime 工具）、朙月拼音方案数据和 python3 的 PyYAML 后重试。'
  fi
  deps_ok || die '依赖安装后仍不完整，请检查 ibus、rime_deployer、luna_pinyin_simp 方案和 python3-yaml。'
fi

if [[ ! -f "${RIME_ENGLISH_WORDLIST:-/usr/share/dict/words}" ]] && command -v apt-get >/dev/null; then
  say '安装英文词表 wamerican（需要 sudo；失败时只启用内置英文词汇）'
  sudo apt-get install -y wamerican || say '英文词表安装失败，继续部署。'
fi

say "下载 $REPO@$BRANCH 到 $DEST"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
curl -fsSL "https://codeload.github.com/$REPO/tar.gz/refs/heads/$BRANCH" | tar -xz -C "$tmp" --strip-components=1
rm -rf "$DEST"
mkdir -p "$(dirname "$DEST")"
mv "$tmp" "$DEST"
trap - EXIT

say '开始部署'
bash "$DEST/deploy.sh" "$@"
