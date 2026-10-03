# Compare Homebrew formula versions with Ruby's native version semantics.
require 'json'
require 'rubygems'

formula = JSON.parse(STDIN.read).fetch('formulae').fetch(0)
installed = formula.fetch('installed')
if installed.empty?
  puts 'install'
elsif formula.fetch('pinned', false)
  puts 'keep'
else
  stable = formula.fetch('versions').fetch('stable')
  raise 'No stable Homebrew version available' unless stable
  revision = formula.fetch('revision', 0)
  target = Gem::Version.new("#{stable}.#{revision}")
  versions = installed.map do |entry|
    # Preserve HEAD and uncomparable builds rather than guessing their age.
    version = entry.fetch('version')
    if version.start_with?('HEAD')
      puts 'keep'
      exit
    end
    base, installed_revision = version.split('_', 2)
    Gem::Version.new("#{base}.#{installed_revision || 0}")
  end
  puts(versions.max >= target ? 'keep' : 'upgrade')
end
