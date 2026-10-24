import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import yaml
from PyQt6.QtWidgets import QApplication, QToolButton, QWidget, QVBoxLayout, QLabel, QScrollArea, QFormLayout
from playlite.providers import GameProvider
from playlite.play_actions import PlayActionsEditor

spec = importlib.util.spec_from_file_location('mangohud_plugin', Path(__file__).resolve().parents[1] / 'plugin.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
APP = QApplication.instance() or QApplication([])


class MangoHudTests(unittest.TestCase):
    def test_advanced_scrolls_instead_of_compressing_controls(self):
        class SteamSettings(QWidget):
            def __init__(self, parent):
                super().__init__(parent)
                label = QLabel('Steam manages the executable, Proton version, and launch options. '
                               'Set launch options in Steam’s game properties.')
                label.setWordWrap(True)
                QVBoxLayout(self).addWidget(label)
            def collect(self):return {}
        class Steam(GameProvider):
            id = 'SteamIntegration';name = 'Steam'
            def create_action_editor(self, action, parent=None):return SteamSettings(parent)
        with patch('playlite.providers.discover_plugins', return_value={'MangoHud': module.Plugin()}):
            scroll = QScrollArea();scroll.setWidgetResizable(True)
            body = QWidget();form = QFormLayout(body)
            editor = PlayActionsEditor({'PlayActions': [dict(Name='Play', Integration='LutrisIntegration', GameId='123')]}, [Steam()])
            form.addRow('Play actions', editor);scroll.setWidget(body)
            scroll.resize(800, 240);scroll.show()
            settings = editor.cards[0].settings
            settings.findChild(QToolButton).setChecked(True)
            settings.contributions[0].toggle.setChecked(True)
            for width in (800, 500, 800):
                scroll.resize(width, 240)
                for _ in range(20):APP.processEvents()
                self.assertGreater(scroll.verticalScrollBar().maximum(), 0)
                toggle = settings.contributions[0].toggle
                self.assertGreaterEqual(toggle.height(), toggle.sizeHint().height())
                for label in settings.findChildren(QLabel):
                    if label.isVisibleTo(settings):
                        self.assertGreaterEqual(label.height(), label.heightForWidth(label.width()))
            scroll.close()

    def test_steam_custom_editor_gets_advanced_controls_and_actions_stay_independent(self):
        class SteamSettings(QWidget):
            def __init__(self, parent):
                super().__init__(parent)
                QVBoxLayout(self).addWidget(QLabel('Steam manages launch options.'))
            def collect(self):return {}
        class Steam(GameProvider):
            id = 'SteamIntegration';name = 'Steam'
            def create_action_editor(self, action, parent=None):return SteamSettings(parent)
        action = dict(Name='Play', Integration='LutrisIntegration', GameId='123')
        with patch('playlite.providers.discover_plugins', return_value={'MangoHud': module.Plugin()}):
            editor = PlayActionsEditor({'PlayActions': [action, dict(action, GameId='456')]}, [Steam()])
            settings = editor.cards[0].settings
            button = settings.findChild(QToolButton)
            button.setChecked(True)
            settings.contributions[0].toggle.setChecked(True)
            self.assertTrue(settings.contributions[0].instructions.isVisibleTo(editor))
            saved = editor.collect()
            self.assertTrue(saved[0]['MangoHud'])
            self.assertNotIn('MangoHud', saved[1])
            editor.deleteLater()

    def test_toggle_roundtrip_under_existing_advanced_section(self):
        provider = GameProvider()
        provider.id = 'LutrisIntegration';provider.name = 'Lutris'
        plugin = module.Plugin()
        action = dict(Name='Default', Integration=provider.id, GameId='1')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'game.yml';path.write_text('system:\n  mangohud: false\n')
            with patch.object(module, 'configuration_path', return_value=path), patch('playlite.providers.discover_plugins', return_value={'MangoHud': plugin}):
                editor = PlayActionsEditor({'PlayActions': [action]}, [provider])
                settings = editor.cards[0].settings
                self.assertFalse(settings.contributions[0].isVisibleTo(editor))
                settings.findChild(QToolButton).setChecked(True)
                self.assertTrue(settings.contributions[0].isVisibleTo(editor))
                settings.contributions[0].toggle.setChecked(True)
                saved = editor.collect()
                self.assertTrue(saved[0]['MangoHud'])
                self.assertNotIn('mangohud: true', path.read_text())
                with plugin.save_action_settings({'PlayActions': saved}):pass
                self.assertTrue(yaml.safe_load(path.read_text())['system']['mangohud'])
                self.assertEqual(len(editor.findChildren(QToolButton)), 1)
                editor.deleteLater()

    def test_preserves_other_lutris_settings_and_supports_disabling(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'game.yml'
            config = {'game': {'args': '--profile custom', 'prefix': '/prefix'},
                      'system': {'env': {'EXTRA_JUMPS_PROFILE': 'custom'}, 'gamemode': False},
                      'wine': {'version': 'ge-proton'}}
            path.write_text(yaml.safe_dump(config));path.chmod(0o640)
            for enabled in [True, False]:
                module.update_config(path, enabled)
                expected = dict(config, system=dict(config['system'], mangohud=enabled))
                self.assertEqual(yaml.safe_load(path.read_text()), expected)
                self.assertEqual(path.stat().st_mode & 0o777, 0o640)
            self.assertEqual(list(Path(folder).iterdir()), [path])

    def test_steam_instructions_and_no_lutris_mutation(self):
        with patch.object(module, 'configuration_path') as configuration:
            widget = module.ActionSettings({'Integration': 'SteamIntegration', 'GameId': '123'})
            self.assertTrue(widget.instructions.isHidden())
            widget.toggle.setChecked(True)
            self.assertFalse(widget.instructions.isHidden())
            self.assertIn('mangohud %command%', widget.instructions.text())
            action = dict(widget.action, **widget.collect())
            with module.Plugin().save_action_settings({'PlayActions': [action]}):pass
            configuration.assert_not_called()
            widget.deleteLater()

    def test_does_not_claim_existing_unmanaged_setting(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'game.yml';path.write_text('system:\n  mangohud: true\n')
            with patch.object(module, 'configuration_path', return_value=path):
                widget = module.ActionSettings({'Integration': 'LutrisIntegration', 'GameId': '1'})
                self.assertTrue(widget.toggle.isChecked())
                self.assertEqual(widget.collect(), {})
                widget.toggle.setChecked(False)
                self.assertEqual(widget.collect(), {'MangoHud': False})
                widget.deleteLater()

    def test_conflicting_actions_for_same_entry_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'game.yml';path.write_text('system: {}\n')
            with patch.object(module, 'configuration_path', return_value=path):
                actions = [dict(Integration='LutrisIntegration', GameId='1', MangoHud=enabled) for enabled in [True, False]]
                with self.assertRaisesRegex(ValueError, 'same MangoHud'):
                    module.Plugin().prepare_edit_save({}, {'PlayActions': actions})
                self.assertEqual(path.read_text(), 'system: {}\n')

    def test_library_failure_rolls_back_launcher_changes(self):
        from playlite.editor import save_game
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'game.yml'
            original = 'system:\n  mangohud: false\n  env:\n    KEEP: unchanged\n'
            path.write_text(original);path.chmod(0o640)
            plugin = module.Plugin()
            game = dict(Id='one', PlayActions=[dict(Integration='LutrisIntegration', GameId='1', MangoHud=True)])
            with patch.object(module, 'configuration_path', return_value=path), \
                    patch('playlite.providers.discover_plugins', return_value={'MangoHud': plugin}), \
                    patch('playlite.game_storage._persist_game', side_effect=OSError('library write failed')):
                with self.assertRaisesRegex(OSError, 'library write failed'):
                    save_game(root, [], game)
            self.assertEqual(path.read_text(), original)
            self.assertEqual(path.stat().st_mode & 0o777, 0o640)

    def test_rollback_preserves_newer_external_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'game.yml';path.write_text('system: {}\n')
            game = {'PlayActions': [dict(Integration='LutrisIntegration', GameId='1', MangoHud=True)]}
            with patch.object(module, 'configuration_path', return_value=path):
                with self.assertRaisesRegex(ValueError, 'newer changes were preserved'):
                    with module.Plugin().save_action_settings(game):
                        path.write_text('system:\n  mangohud: false\n  gamemode: true\n')
                        raise OSError('library write failed')
            self.assertTrue(yaml.safe_load(path.read_text())['system']['gamemode'])
