#!/usr/bin/env bash
# install.sh — 一鍵安裝並部署 NotebookLM Slack Bot
#
# 執行方式：
#   bash docs/examples/install.sh
#
# 此腳本會：
#   1. 建立 Python 虛擬環境並安裝依賴
#   2. 執行 notebooklm login（如尚未認證）
#   3. 建立 ~/.notebooklm/.env.slack（如不存在）
#   4. 建立並啟動 systemd 服務（僅 Linux）
set -euo pipefail

# ---------------------------------------------------------------------------
# 路徑設定
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
BOT_SCRIPT="$SCRIPT_DIR/slack_notebooklm_bot.py"
VENV_DIR="$REPO_DIR/.venv"
ENV_FILE="${NOTEBOOKLM_HOME:-$HOME/.notebooklm}/.env.slack"
ENV_EXAMPLE="$SCRIPT_DIR/.env.slack.example"
SERVICE_NAME="notebooklm-slack-bot"
SERVICE_SRC="$SCRIPT_DIR/notebooklm-slack-bot.service"
SERVICE_DEST="/etc/systemd/system/$SERVICE_NAME.service"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()    { echo -e "${GREEN}[✓]${NC} $*"; }
warn()    { echo -e "${YELLOW}[!]${NC} $*"; }
error()   { echo -e "${RED}[✗]${NC} $*" >&2; exit 1; }
section() { echo -e "\n${YELLOW}=== $* ===${NC}"; }

# ---------------------------------------------------------------------------
# 1. 確認 Python 3.10+
# ---------------------------------------------------------------------------
section "檢查 Python 版本"
PYTHON=""
for candidate in python3 python3.13 python3.12 python3.11 python3.10; do
    if command -v "$candidate" &>/dev/null; then
        ver=$("$candidate" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        major=${ver%%.*}; minor=${ver#*.}
        if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
            PYTHON=$(command -v "$candidate")
            break
        fi
    fi
done
[ -z "$PYTHON" ] && error "需要 Python 3.10 或更新版本，請先安裝。"
info "使用 Python: $PYTHON ($ver)"

# ---------------------------------------------------------------------------
# 2. 建立虛擬環境並安裝依賴
# ---------------------------------------------------------------------------
section "安裝 Python 依賴"

# 優先使用 uv（如已安裝）
if command -v uv &>/dev/null && [ ! -d "$VENV_DIR" ]; then
    info "使用 uv 建立虛擬環境…"
    uv venv "$VENV_DIR"
    info "安裝套件 (notebooklm-py[claude,slack])…"
    uv pip install --python "$VENV_DIR/bin/python" -e "$REPO_DIR[claude,slack]"
elif [ ! -d "$VENV_DIR" ]; then
    info "建立虛擬環境 (.venv)…"
    "$PYTHON" -m venv "$VENV_DIR"
    info "安裝套件 (notebooklm-py[claude,slack])…"
    "$VENV_DIR/bin/pip" install --quiet -e "$REPO_DIR[claude,slack]"
else
    info "虛擬環境已存在，更新套件…"
    "$VENV_DIR/bin/pip" install --quiet -e "$REPO_DIR[claude,slack]"
fi

VENV_PYTHON="$VENV_DIR/bin/python"
VENV_NLM="$VENV_DIR/bin/notebooklm"
info "虛擬環境 Python: $VENV_PYTHON"

# ---------------------------------------------------------------------------
# 3. Google NotebookLM 認證
# ---------------------------------------------------------------------------
section "Google 認證"
NLM_HOME="${NOTEBOOKLM_HOME:-$HOME/.notebooklm}"
if [ -f "$NLM_HOME/storage_state.json" ] || \
   [ -f "$NLM_HOME/profiles/default/storage_state.json" ]; then
    info "已找到認證檔案，跳過登入。"
else
    warn "尚未登入，即將開啟瀏覽器進行 Google 登入…"
    "$VENV_NLM" login
    info "登入完成。"
fi

# ---------------------------------------------------------------------------
# 4. 建立環境變數檔案
# ---------------------------------------------------------------------------
section "設定環境變數"
mkdir -p "$(dirname "$ENV_FILE")"

if [ -f "$ENV_FILE" ]; then
    info "環境變數檔案已存在：$ENV_FILE"
else
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    warn "已建立環境變數範本：$ENV_FILE"
    warn "請用編輯器填入你的 Slack tokens 和 Anthropic API key："
    warn "  nano $ENV_FILE"
    echo ""
    echo "  必填欄位："
    echo "    SLACK_BOT_TOKEN=xoxb-..."
    echo "    SLACK_APP_TOKEN=xapp-..."
    echo "    ANTHROPIC_API_KEY=sk-ant-..."
    echo ""
fi

# 確認必填的 token 已設定
source "$ENV_FILE" 2>/dev/null || true
missing=()
[ -z "${SLACK_BOT_TOKEN:-}" ] && missing+=("SLACK_BOT_TOKEN")
[ -z "${SLACK_APP_TOKEN:-}" ]  && missing+=("SLACK_APP_TOKEN")
[ -z "${ANTHROPIC_API_KEY:-}" ] && missing+=("ANTHROPIC_API_KEY")

if [ ${#missing[@]} -gt 0 ]; then
    warn "以下環境變數尚未設定："
    for v in "${missing[@]}"; do echo "  - $v"; done
    warn "請先填入 $ENV_FILE 再繼續安裝 systemd 服務。"
    echo ""
    echo "填完後重新執行此腳本，或手動啟動 bot："
    echo "  source $ENV_FILE && $VENV_PYTHON $BOT_SCRIPT"
    exit 0
fi

# ---------------------------------------------------------------------------
# 5. 安裝 systemd 服務（Linux only）
# ---------------------------------------------------------------------------
section "設定 systemd 服務"

if [[ "$(uname -s)" != "Linux" ]]; then
    warn "非 Linux 系統，跳過 systemd 設定。"
    info "手動啟動指令："
    echo "  source $ENV_FILE && $VENV_PYTHON $BOT_SCRIPT"
    exit 0
fi

if ! command -v systemctl &>/dev/null; then
    warn "找不到 systemctl，跳過 systemd 設定。"
    info "手動啟動指令："
    echo "  source $ENV_FILE && $VENV_PYTHON $BOT_SCRIPT"
    exit 0
fi

CURRENT_USER="$(whoami)"
USER_HOME="$HOME"

# 填入實際路徑
info "建立 systemd service 檔案：$SERVICE_DEST"
sudo sed \
    -e "s|__USER__|$CURRENT_USER|g" \
    -e "s|__HOME__|$USER_HOME|g" \
    -e "s|__PYTHON__|$VENV_PYTHON|g" \
    -e "s|__BOT_SCRIPT__|$BOT_SCRIPT|g" \
    "$SERVICE_SRC" | sudo tee "$SERVICE_DEST" > /dev/null

sudo chmod 644 "$SERVICE_DEST"
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"

echo ""
info "Bot 已啟動！"
echo ""
echo "常用指令："
echo "  查看狀態：  sudo systemctl status $SERVICE_NAME"
echo "  查看日誌：  journalctl -u $SERVICE_NAME -f"
echo "  重新啟動：  sudo systemctl restart $SERVICE_NAME"
echo "  停止：      sudo systemctl stop $SERVICE_NAME"
echo "  開機自啟：  sudo systemctl enable $SERVICE_NAME  (已設定)"
echo ""
sudo systemctl status "$SERVICE_NAME" --no-pager -l || true
