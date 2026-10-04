# Defaults can be overridden before this file is sourced in .zshrc.
export ZSH="$HOME/.oh-my-zsh"
if (( ! ${+ZSH_THEME} )); then
  ZSH_THEME=robbyrussell
fi
if (( ! ${+plugins} )); then
  plugins=(git z)
fi
# machine-setup updates this checkout; avoid a second updater at shell startup.
zstyle ':omz:update' mode disabled
source "$ZSH/oh-my-zsh.sh"
