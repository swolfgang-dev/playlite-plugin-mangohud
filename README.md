# MangoHud for Playlite

Development-only plugin. It is excluded from the release catalogue, and its
workflow runs tests without building or publishing releases.

Adds **Enable MangoHud** under each play action's **Advanced launch settings**.
Lutris actions update only the selected Lutris entry's `system.mangohud` setting
when the game edit is saved. Steam actions show instructions for enabling the
overlay in that game's Steam launch options; Steam settings are never edited.

Requires Playlite's `GenericPlugin.create_action_settings` extension point,
core Lutris support for Lutris actions, and MangoHud installed for the game runner.
No overlay settings are enabled automatically by installing this plugin.

MangoHud settings apply to a Lutris entry, so actions using the same Lutris ID
must agree. Existing arguments, Wine settings, prefixes, and environment variables
are retained. Removing the plugin leaves the user's Lutris setting in place.
