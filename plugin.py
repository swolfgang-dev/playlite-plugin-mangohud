"""Per-action MangoHud controls and narrow Lutris configuration updates."""
import os
from pathlib import Path
import sqlite3
import stat
import tempfile

import yaml
from PyQt6.QtCore import Qt
from playlite.action_settings import update_action_files
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QCheckBox, QLabel
from playlite.providers import GenericPlugin
from playlite.theme import set_style


def configuration_path(identity, database=None):
    from playlite.lutris_library import configuration_path as locate
    return locate(database, identity)


def read_config(path):
    config = yaml.safe_load(path.read_text())
    if not isinstance(config, dict) or not isinstance(config.get('system', {}), dict):
        raise ValueError('The Lutris configuration has invalid system settings.')
    return config


def update_config(path, enabled):
    original = path.read_bytes()
    config = read_config(path)
    system = config.setdefault('system', {})
    if system.get('mangohud') is enabled:
        return
    system['mangohud'] = enabled
    encoded = yaml.safe_dump(config, sort_keys=False).encode()
    descriptor, temporary = tempfile.mkstemp(prefix='.mangohud-', dir=path.parent)
    try:
        os.fchmod(descriptor, stat.S_IMODE(path.stat().st_mode))
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        if path.read_bytes() != original:
            raise ValueError('Lutris settings changed while saving. Reopen the game editor and retry.')
        os.replace(temporary, path)
        return encoded
    finally:
        if os.path.exists(temporary):os.unlink(temporary)


class ActionSettings(QWidget):
    def __init__(self, action, parent=None):
        super().__init__(parent)
        self.setObjectName('mangoHudActionSettings')
        set_style(self, 'QWidget#mangoHudActionSettings, QWidget#mangoHudActionSettings QCheckBox, '
                  'QWidget#mangoHudActionSettings QLabel { background: transparent; border: 0; }')
        self.action = action
        self.initial = action.get('MangoHud')
        error = ''
        if action['Integration'] == 'LutrisIntegration':
            try:
                current = read_config(configuration_path(action.get('GameId'), action.get('LutrisDatabase'))).get('system', {}).get('mangohud', False)
                self.initial = bool(current)
            except (ValueError, OSError, sqlite3.Error, yaml.YAMLError) as failure:
                error = str(failure)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 4, 0, 8)
        layout.setSpacing(8)
        self.toggle = QCheckBox('Enable MangoHud', self)
        self.toggle.setChecked(self.initial is True)
        self.toggle.setToolTip('Show the MangoHud performance overlay when this action launches.')
        layout.addWidget(self.toggle)
        self.instructions = QLabel(self)
        self.instructions.setContentsMargins(28, 0, 0, 0)
        self.instructions.setWordWrap(True)
        self.instructions.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        if action['Integration'] == 'SteamIntegration':
            self.instructions.setText('In Steam, right-click this game → Properties → General → Launch Options. '
                'Add mangohud before %command% (for example: mangohud %command%). '
                'Keep your existing launch options. To disable it, remove mangohud there. '
                'This checkbox does not change Steam settings.')
            self.toggle.toggled.connect(self.instructions.setVisible)
            self.instructions.setVisible(self.toggle.isChecked())
        else:
            self.instructions.setText(error or 'Updates this Lutris entry when you save. MangoHud must be installed. '
                'If the game is running, the change applies on its next launch.')
        layout.addWidget(self.instructions)

    def collect(self):
        # Do not claim an unmanaged Lutris setting just by opening the editor.
        if self.toggle.isChecked() == (self.initial is True) and 'MangoHud' not in self.action:
            return {}
        return {'MangoHud': self.toggle.isChecked()}


class Plugin(GenericPlugin):
    def create_action_settings(self, action, parent=None):
        if action.get('Integration') in ('LutrisIntegration', 'SteamIntegration'):
            return ActionSettings(action, parent)
        return None

    def changes(self, game):
        changes = {}
        for action in game.get('PlayActions', []):
            if action.get('Integration') != 'LutrisIntegration' or 'MangoHud' not in action:
                continue
            enabled = action['MangoHud']
            if type(enabled) is not bool:
                raise ValueError('MangoHud must be enabled or disabled.')
            path = configuration_path(action.get('GameId'), action.get('LutrisDatabase'))
            if path in changes and changes[path] != enabled:
                raise ValueError('Actions sharing one Lutris entry must use the same MangoHud setting.')
            read_config(path)
            changes[path] = enabled
        return changes

    def prepare_edit_save(self, previous, game):
        self.changes(game)

    def save_action_settings(self, game):
        """Commit launcher changes with the library instead of after its save."""
        return update_action_files(self.changes(game), update_config)
