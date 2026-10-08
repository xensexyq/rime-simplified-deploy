#!/usr/bin/env bash
# One-command deployment for an existing Fcitx5 + Rime Ice desktop:
#   bash <(curl -fsSL https://raw.githubusercontent.com/xensexyq/rime-simplified-deploy/main/install.sh)
# Extra arguments are forwarded to deploy.sh, for example --set-default.
set -euo pipefail

REPO="${RIME_DEPLOY_REPO:-xensexyq/rime-simplified-deploy}"
BRANCH="${RIME_DEPLOY_BRANCH:-main}"
DEST="${RIME_DEPLOY_HOME:-$HOME/.local/share/rime-simplified-deploy}"
rime_dir="${RIME_USER_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/fcitx5/rime}"
python_bin="${RIME_PYTHON:-/usr/bin/python3}"

say() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m错误：\033[0m%s\n' "$*" >&2; exit 1; }

[[ $EUID -ne 0 ]] || die '请以当前桌面用户运行，不要使用 sudo/root。'
command -v curl >/dev/null || die '请先安装 curl。'
command -v tar >/dev/null || die '请先安装 tar。'

case "$DEST" in
  ''|/|"$HOME") die 'RIME_DEPLOY_HOME 不能指向空路径、根目录或用户主目录。' ;;
esac

runtime_ok() {
  command -v fcitx5-remote >/dev/null && command -v rime_deployer >/dev/null     && "$python_bin" -c 'import yaml' 2>/dev/null
}

if ! runtime_ok; then
  if command -v apt-get >/dev/null; then
    say '安装 Fcitx5 Rime 及部署依赖（需要 sudo）'
    sudo apt-get update
    sudo apt-get install -y fcitx5 fcitx5-rime librime-bin python3-yaml wamerican
  else
    die '缺少依赖。请用系统包管理器安装 fcitx5、fcitx5-rime、rime_deployer 和 Python PyYAML 后重试。'
  fi
  runtime_ok || die '依赖安装后仍不完整，请检查 fcitx5-remote、rime_deployer 和 python3-yaml。'
fi

[[ -f "$rime_dir/rime_ice.schema.yaml" ]]   || die "未检测到雾凇拼音：$rime_dir/rime_ice.schema.yaml。请先安装并部署 iDvel/rime-ice。"

if [[ ! -f "${RIME_ENGLISH_WORDLIST:-/usr/share/dict/words}" ]] && command -v apt-get >/dev/null; then
  say '安装英文词表 wamerican（需要 sudo；失败时只启用内置英文术语）'
  sudo apt-get install -y wamerican || say '英文词表安装失败，继续部署内置英文术语。'
fi

say "下载 $REPO@$BRANCH 到 $DEST"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
curl -fsSL "https://codeload.github.com/$REPO/tar.gz/refs/heads/$BRANCH"   | tar -xz -C "$tmp" --strip-components=1

mkdir -p "$(dirname "$DEST")"
if [[ -e "$DEST" ]]; then
  backup="${DEST}.bak-$(date +%Y%m%d-%H%M%S-%N)"
  mv "$DEST" "$backup"
  say "原安装目录已备份到 $backup"
fi
mv "$tmp" "$DEST"
trap - EXIT

say '开始部署到 Fcitx5 雾凇拼音'
bash "$DEST/deploy.sh" "$@"
