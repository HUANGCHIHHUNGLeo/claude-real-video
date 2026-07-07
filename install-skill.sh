#!/usr/bin/env bash
# install-skill.sh — Install claude-real-video skill into AI agent platforms
# Default install path: $HOME/.agents/skills
# Auto-detects: Claude Code, Codex, Gemini CLI, OpenCode, Pi

set -euo pipefail

SKILL_NAME="claude-real-video-for-agents"
DEFAULT_INSTALL_DIR="$HOME/.agents/skills"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_SOURCE="$SCRIPT_DIR/skills/$SKILL_NAME"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "${BLUE}[info]${NC} $*"; }
ok()    { echo -e "${GREEN}[ok]${NC} $*"; }
warn()  { echo -e "${YELLOW}[warn]${NC} $*"; }
err()   { echo -e "${RED}[error]${NC} $*" >&2; }

# --- Validate source ---
if [[ ! -d "$SKILL_SOURCE" ]]; then
    err "Skill source not found: $SKILL_SOURCE"
    err "Run this script from the claude-real-video repo root."
    exit 1
fi

if [[ ! -f "$SKILL_SOURCE/SKILL.md" ]]; then
    err "SKILL.md not found in $SKILL_SOURCE"
    exit 1
fi

echo -e "${BOLD}${CYAN}"
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║   claude-real-video — Agent Skill Installer              ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# --- Step 1: Install to default path ---
info "Installing skill to ${BOLD}$DEFAULT_INSTALL_DIR/$SKILL_NAME${NC}"
mkdir -p "$DEFAULT_INSTALL_DIR"

if [[ -e "$DEFAULT_INSTALL_DIR/$SKILL_NAME" ]]; then
    warn "Existing install found at $DEFAULT_INSTALL_DIR/$SKILL_NAME"
    read -rp "  Overwrite? [y/N] " answer
    if [[ "$answer" =~ ^[Yy]$ ]]; then
        rm -rf "$DEFAULT_INSTALL_DIR/$SKILL_NAME"
    else
        info "Skipping default install."
    fi
fi

if [[ ! -e "$DEFAULT_INSTALL_DIR/$SKILL_NAME" ]]; then
    cp -r "$SKILL_SOURCE" "$DEFAULT_INSTALL_DIR/$SKILL_NAME"
    ok "Installed to $DEFAULT_INSTALL_DIR/$SKILL_NAME"
else
    ok "Default install preserved."
fi

echo ""

# --- Step 2: Auto-detect agent platforms ---
declare -a DETECTED_NAMES=()
declare -a DETECTED_PATHS=()

# Claude Code
CLAUDE_SKILL_DIR="$HOME/.claude/skills"
if [[ -d "$HOME/.claude" ]]; then
    DETECTED_NAMES+=("Claude Code")
    DETECTED_PATHS+=("$CLAUDE_SKILL_DIR")
fi

# Codex
CODEX_SKILL_DIR="$HOME/.codex/skills"
if [[ -d "$HOME/.codex" ]]; then
    DETECTED_NAMES+=("Codex")
    DETECTED_PATHS+=("$CODEX_SKILL_DIR")
fi

# Gemini CLI
GEMINI_SKILL_DIR="$HOME/.gemini/skills"
if [[ -d "$HOME/.gemini" ]]; then
    DETECTED_NAMES+=("Gemini CLI")
    DETECTED_PATHS+=("$GEMINI_SKILL_DIR")
fi

# OpenCode
OPENCODE_SKILL_DIR="$HOME/.opencode/skills"
if [[ -d "$HOME/.opencode" ]]; then
    DETECTED_NAMES+=("OpenCode")
    DETECTED_PATHS+=("$OPENCODE_SKILL_DIR")
fi

# Pi (pi.dev)
PI_SKILL_DIR="$HOME/.pi/skills"
if [[ -d "$HOME/.pi" ]]; then
    DETECTED_NAMES+=("Pi")
    DETECTED_PATHS+=("$PI_SKILL_DIR")
fi

# MiMoCode
MIMOCODE_SKILL_DIR="$HOME/.mimocode/skills"
if [[ -d "$HOME/.mimocode" ]]; then
    DETECTED_NAMES+=("MiMoCode")
    DETECTED_PATHS+=("$MIMOCODE_SKILL_DIR")
fi

# Agents (generic)
AGENTS_SKILL_DIR="$HOME/.agents/skills"
if [[ -d "$HOME/.agents" ]]; then
    DETECTED_NAMES+=("Agents (.agents)")
    DETECTED_PATHS+=("$AGENTS_SKILL_DIR")
fi

if [[ ${#DETECTED_NAMES[@]} -eq 0 ]]; then
    info "No agent platforms detected. Skill installed to $DEFAULT_INSTALL_DIR only."
    echo ""
    info "To manually install later, symlink or copy:"
    echo "  ln -s $DEFAULT_INSTALL_DIR/$SKILL_NAME ~/.claude/skills/$SKILL_NAME"
    echo ""
    exit 0
fi

info "Detected ${BOLD}${#DETECTED_NAMES[@]}${NC} agent platform(s):"
for i in "${!DETECTED_NAMES[@]}"; do
    echo -e "  ${CYAN}$((i+1))${NC}. ${DETECTED_NAMES[$i]}  →  ${DETECTED_PATHS[$i]}"
done

echo ""
info "Symlink the skill into detected platforms?"
echo -e "  ${GREEN}a${NC} = all, ${GREEN}n${NC} = none, ${GREEN}1 2 3${NC} = pick by number"
echo ""

read -rp "  Your choice [a/n/numbers]: " choice

declare -a SELECTED_IDX=()

if [[ "$choice" =~ ^[Aa]$ ]]; then
    for i in "${!DETECTED_NAMES[@]}"; do
        SELECTED_IDX+=("$i")
    done
elif [[ "$choice" =~ ^[Nn]$ ]]; then
    info "Skipping symlinks."
else
    for num in $choice; do
        if [[ "$num" =~ ^[0-9]+$ ]] && (( num >= 1 && num <= ${#DETECTED_NAMES[@]} )); then
            SELECTED_IDX+=("$((num-1))")
        else
            warn "Ignoring invalid selection: $num"
        fi
    done
fi

echo ""

LINK_COUNT=0
for i in "${SELECTED_IDX[@]}"; do
    target_dir="${DETECTED_PATHS[$i]}"
    target_link="$target_dir/$SKILL_NAME"
    platform="${DETECTED_NAMES[$i]}"

    mkdir -p "$target_dir"

    if [[ -L "$target_link" ]]; then
        existing=$(readlink "$target_link")
        if [[ "$existing" == "$DEFAULT_INSTALL_DIR/$SKILL_NAME" ]]; then
            ok "Already linked: $platform"
            continue
        else
            warn "Removing stale symlink at $target_link (pointed to $existing)"
            rm "$target_link"
        fi
    elif [[ -e "$target_link" ]]; then
        warn "Existing directory at $target_link — skipping $platform"
        continue
    fi

    ln -s "$DEFAULT_INSTALL_DIR/$SKILL_NAME" "$target_link"
    ok "Symlinked → $platform ($target_link)"
    LINK_COUNT=$((LINK_COUNT + 1))
done

echo ""

# --- Summary ---
echo -e "${BOLD}${GREEN}Done!${NC}"
echo ""
echo "  Installed: $DEFAULT_INSTALL_DIR/$SKILL_NAME"
if (( LINK_COUNT > 0 )); then
    echo "  Symlinks:  $LINK_COUNT platform(s)"
fi
echo ""
info "To use: paste a video URL into your agent and ask about it."
info "The agent will automatically detect the skill and run crv."
echo ""
info "Manual install for other platforms:"
echo "  ln -s $DEFAULT_INSTALL_DIR/$SKILL_NAME ~/.<agent>/skills/$SKILL_NAME"
echo ""
