"""
Dialogo para editar as configuracoes de um jogo ja cadastrado.
"""

import os

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)


class GameSettingsDialog(QDialog):
    """Permite editar executavel, save folder e opcoes de sync do jogo."""

    def __init__(
        self, game, sync_enabled: bool, global_sync_enabled: bool, parent=None
    ):
        super().__init__(parent)
        self.result_data = None
        self.sync_now_requested = False
        self._global_sync_enabled = global_sync_enabled

        self.setWindowTitle(f"Configurar Jogo - {game.name}")
        self.setMinimumSize(640, 320)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        group = QGroupBox("CONFIGURACOES DO JOGO")
        form = QFormLayout(group)

        self._name_input = QLineEdit(game.name)
        self._name_input.setPlaceholderText("Nome do jogo")
        form.addRow("Nome:", self._name_input)

        exe_row = QHBoxLayout()
        self._exe_input = QLineEdit(game.executable_path)
        self._exe_input.setPlaceholderText("Caminho do executavel")
        exe_row.addWidget(self._exe_input)

        exe_btn = QPushButton("Procurar...")
        exe_btn.clicked.connect(self._browse_executable)
        exe_row.addWidget(exe_btn)
        form.addRow("Executavel:", exe_row)

        save_row = QHBoxLayout()
        self._save_input = QLineEdit(game.save_folder)
        self._save_input.setPlaceholderText("Pasta de saves")
        self._save_input.textChanged.connect(self._update_sync_controls)
        save_row.addWidget(self._save_input)

        save_btn = QPushButton("Procurar...")
        save_btn.clicked.connect(self._browse_save_folder)
        save_row.addWidget(save_btn)
        form.addRow("Pasta de Saves:", save_row)

        self._sync_enabled = QCheckBox("Ativar sync de saves para este jogo")
        self._sync_enabled.setChecked(sync_enabled)
        form.addRow("", self._sync_enabled)

        layout.addWidget(group)

        self._info_label = QLabel("")
        self._info_label.setWordWrap(True)
        self._info_label.setStyleSheet("color: #9aa4b2; font-size: 12px;")
        layout.addWidget(self._info_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancelar")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        self._sync_now_btn = QPushButton("Salvar e Sincronizar Agora")
        self._sync_now_btn.clicked.connect(lambda: self._finish(sync_now=True))
        btn_row.addWidget(self._sync_now_btn)

        save_btn = QPushButton("Salvar")
        save_btn.clicked.connect(lambda: self._finish(sync_now=False))
        btn_row.addWidget(save_btn)

        layout.addLayout(btn_row)
        self._update_sync_controls()

    def _browse_executable(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Selecionar Executavel",
            self._exe_input.text().strip(),
            "Executaveis (*.exe);;Todos (*.*)",
        )
        if path:
            self._exe_input.setText(path)

    def _browse_save_folder(self):
        path = QFileDialog.getExistingDirectory(
            self,
            "Selecionar Pasta de Saves",
            self._save_input.text().strip(),
        )
        if path:
            self._save_input.setText(path)

    def _update_sync_controls(self):
        has_save_folder = bool(self._save_input.text().strip())
        if not has_save_folder:
            self._sync_enabled.setChecked(False)

        self._sync_enabled.setEnabled(has_save_folder)
        self._sync_now_btn.setEnabled(has_save_folder)

        if not has_save_folder:
            self._info_label.setText(
                "Defina uma pasta de saves para habilitar a sincronizacao deste jogo."
            )
            return

        if self._global_sync_enabled:
            self._info_label.setText(
                "Sincronizacao de saves ativada. Use o botao 'Sincronizar' na biblioteca ou 'Salvar e Sincronizar Agora' para realizar o sincronismo manual."
            )
        else:
            self._info_label.setText(
                "A sincronizacao global de saves esta desligada nas Configuracoes. Voce ainda pode clicar em 'Salvar e Sincronizar Agora' para sincronizar de imediato."
            )

    def _finish(self, sync_now: bool):
        name = self._name_input.text().strip()
        executable_path = self._exe_input.text().strip()
        save_folder = self._save_input.text().strip()
        sync_enabled = self._sync_enabled.isChecked()

        if not name:
            QMessageBox.warning(self, "Erro", "Informe o nome do jogo.")
            return

        if not executable_path:
            QMessageBox.warning(self, "Erro", "Informe o executavel do jogo.")
            return

        if not os.path.isfile(executable_path):
            QMessageBox.warning(self, "Erro", "O executavel informado nao existe.")
            return

        if save_folder and not os.path.isdir(save_folder):
            QMessageBox.warning(self, "Erro", "A pasta de saves informada nao existe.")
            return

        if sync_enabled and not save_folder:
            QMessageBox.warning(
                self,
                "Erro",
                "Defina uma pasta de saves antes de ativar a sincronizacao.",
            )
            return

        self.sync_now_requested = sync_now
        self.result_data = {
            "name": name,
            "executable_path": executable_path,
            "save_folder": save_folder,
            "sync_enabled": sync_enabled,
        }
        self.accept()
