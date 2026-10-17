# Defaults can be overridden before this file is sourced in .zshrc.
export ZSH="$HOME/.oh-my-zsh"
if (( ! ${+ZSH_THEME} )); then
  ZSH_THEME=agnoster
fi
if (( ! ${+plugins} )); then
  plugins=(git z)
fi
# machine-setup updates this checkout; avoid a second updater at shell startup.
zstyle ':omz:update' mode disabled
source "$ZSH/oh-my-zsh.sh"
# Load independently of plugins=(...) so personal plugin lists keep autosuggestions.
# A user may already load it through Oh My Zsh; avoid sourcing it twice.
if (( ! $+functions[_zsh_autosuggest_start] )); then
  source "$ZSH/custom/plugins/zsh-autosuggestions/zsh-autosuggestions.zsh"
fi
