import subprocess
import os
import sys
import threading
from pathlib import Path
from tkinter import (
    Tk, Frame, Label, Button, StringVar, IntVar,
    filedialog, messagebox, ttk, Entry, END
)


class ConversorMP3:
    def __init__(self):
        self.root = Tk()
        self.root.title("MP3 Converter — 128kbps → 64kbps")
        self.root.geometry("580x420")
        self.root.resizable(False, False)
        self.root.configure(bg="#1a1a2e")

        self.pasta_origem = StringVar(value="")
        self.pasta_destino = StringVar(value="")
        self.bitrate_saida = StringVar(value="64k")
        self.status_text = StringVar(value="Selecione as pastas para começar.")
        self.progresso_valor = IntVar(value=0)

        self._construir_interface()

    # ──────────────────────────────────────────────
    #  INTERFACE
    # ──────────────────────────────────────────────
    def _construir_interface(self):
        bg = "#1a1a2e"
        fg = "#e0e0e0"
        accent = "#e94560"
        surface = "#16213e"

        # ---- Título ----
        Label(
            self.root, text="🎵 Conversor de MP3",
            font=("Segoe UI", 18, "bold"),
            bg=bg, fg=accent
        ).pack(pady=(20, 5))

        Label(
            self.root, text="Converta seus arquivos MP3 para bitrates menores",
            font=("Segoe UI", 9),
            bg=bg, fg="#7a7a8e"
        ).pack(pady=(0, 15))

        # ---- Frame de seleção ----
        frame = Frame(self.root, bg=surface, padx=20, pady=15,
                       highlightbackground="#2a2a4a", highlightthickness=1)
        frame.pack(padx=25, fill="x")

        # Pasta de origem
        Label(frame, text="Pasta de origem:", font=("Segoe UI", 10, "bold"),
              bg=surface, fg=fg, anchor="w").grid(row=0, column=0, sticky="w", pady=(0, 4))

        row1 = Frame(frame, bg=surface)
        row1.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        frame.columnconfigure(0, weight=1)

        Entry(row1, textvariable=self.pasta_origem, font=("Consolas", 10),
              bg="#0f3460", fg=fg, insertbackground=fg,
              relief="flat", bd=0).pack(side="left", fill="x", expand=True, ipady=6)

        Button(row1, text="Procurar", font=("Segoe UI", 9, "bold"),
               bg=accent, fg="white", relief="flat", bd=0, padx=12,
               activebackground="#c73650", cursor="hand2",
               command=self._selecionar_origem).pack(side="right", padx=(8, 0))

        # Pasta de destino
        Label(frame, text="Pasta de destino:", font=("Segoe UI", 10, "bold"),
              bg=surface, fg=fg, anchor="w").grid(row=2, column=0, sticky="w", pady=(0, 4))

        row2 = Frame(frame, bg=surface)
        row2.grid(row=3, column=0, sticky="ew", pady=(0, 10))

        Entry(row2, textvariable=self.pasta_destino, font=("Consolas", 10),
              bg="#0f3460", fg=fg, insertbackground=fg,
              relief="flat", bd=0).pack(side="left", fill="x", expand=True, ipady=6)

        Button(row2, text="Procurar", font=("Segoe UI", 9, "bold"),
               bg=accent, fg="white", relief="flat", bd=0, padx=12,
               activebackground="#c73650", cursor="hand2",
               command=self._selecionar_destino).pack(side="right", padx=(8, 0))

        # Bitrate
        row3 = Frame(frame, bg=surface)
        row3.grid(row=4, column=0, sticky="w")

        Label(row3, text="Bitrate de saída:", font=("Segoe UI", 10, "bold"),
              bg=surface, fg=fg).pack(side="left")

        for br in ["32k", "48k", "64k", "96k", "128k"]:
            Button(
                row3, text=br, font=("Segoe UI", 9),
                bg="#0f3460" if br != "64k" else accent,
                fg="white", relief="flat", bd=0, padx=10, pady=3,
                cursor="hand2",
                command=lambda b=br: self._selecionar_bitrate(b)
            ).pack(side="left", padx=(8, 0))

        self._botoes_bitrate = row3

        # ---- Barra de progresso ----
        self.progresso = ttk.Progressbar(
            self.root, variable=self.progresso_valor,
            maximum=100, mode="determinate", length=530
        )
        self.progresso.pack(pady=(20, 5))

        Label(self.root, textvariable=self.status_text,
              font=("Segoe UI", 9), bg=bg, fg="#7a7a8e",
              wraplength=530).pack()

        # ---- Botão converter ----
        self.btn_converter = Button(
            self.root, text="CONVERTER", font=("Segoe UI", 12, "bold"),
            bg=accent, fg="white", relief="flat", bd=0,
            padx=40, pady=8, cursor="hand2",
            activebackground="#c73650",
            command=self._iniciar_conversao
        )
        self.btn_converter.pack(pady=(18, 20))

    # ──────────────────────────────────────────────
    #  AÇÕES DOS BOTÕES
    # ──────────────────────────────────────────────
    def _selecionar_origem(self):
        pasta = filedialog.askdirectory(title="Selecione a pasta com os MP3")
        if pasta:
            self.pasta_origem.set(pasta)
            count = len(list(Path(pasta).glob("*.mp3")))
            self.status_text.set(f"Pasta de origem: {count} arquivo(s) MP3 encontrado(s).")

            # Auto-preenche destino se vazio
            if not self.pasta_destino.get():
                self.pasta_destino.set(str(Path(pasta) / "convertidos"))

    def _selecionar_destino(self):
        pasta = filedialog.askdirectory(title="Selecione a pasta de destino")
        if pasta:
            self.pasta_destino.set(pasta)

    def _selecionar_bitrate(self, bitrate):
        self.bitrate_saida.set(bitrate)
        for widget in self._botoes_bitrate.winfo_children():
            if isinstance(widget, Button):
                if widget.cget("text") == bitrate:
                    widget.configure(bg="#e94560")
                else:
                    widget.configure(bg="#0f3460")

    # ──────────────────────────────────────────────
    #  CONVERSÃO
    # ──────────────────────────────────────────────
    def _iniciar_conversao(self):
        origem = self.pasta_origem.get().strip()
        destino = self.pasta_destino.get().strip()

        if not origem:
            messagebox.showwarning("Aviso", "Selecione a pasta de origem.")
            return
        if not destino:
            messagebox.showwarning("Aviso", "Selecione a pasta de destino.")
            return
        if not Path(origem).exists():
            messagebox.showerror("Erro", "Pasta de origem não existe.")
            return

        arquivos = list(Path(origem).glob("*.mp3"))
        if not arquivos:
            messagebox.showinfo("Aviso", "Nenhum arquivo .mp3 encontrado na pasta de origem.")
            return

        # Desativa o botão durante a conversão
        self.btn_converter.configure(state="disabled", text="CONVERTENDO...")
        self.progresso_valor.set(0)

        # Roda em thread separada pra não travar a interface
        thread = threading.Thread(
            target=self._executar_conversao,
            args=(arquivos, destino),
            daemon=True
        )
        thread.start()

    def _executar_conversao(self, arquivos, destino):
        Path(destino).mkdir(parents=True, exist_ok=True)
        bitrate = self.bitrate_saida.get()
        total = len(arquivos)
        sucesso = 0
        falha = 0

        for i, arquivo in enumerate(arquivos):
            nome_saida = arquivo.stem + f"_{bitrate}.mp3"
            caminho_saida = str(Path(destino) / nome_saida)
            tamanho_antes = os.path.getsize(arquivo) / 1024

            self.status_text.set(f"Convertendo: {arquivo.name}")
            self.root.update_idletasks()

            ok = self._converter_arquivo(str(arquivo), caminho_saida, bitrate)

            if ok:
                tamanho_depois = os.path.getsize(caminho_saida) / 1024
                sucesso += 1
            else:
                falha += 1

            progresso = int((i + 1) / total * 100)
            self.progresso_valor.set(progresso)
            self.root.update_idletasks()

        msg = f"Concluído! {sucesso} convertido(s), {falha} falha(s)."
        self.status_text.set(msg)
        self.btn_converter.configure(state="normal", text="CONVERTER")
        messagebox.showinfo("Finalizado", msg)

    @staticmethod
    def _converter_arquivo(entrada, saida, bitrate):
        comando = [
            "ffmpeg", "-i", entrada,
            "-b:a", bitrate,
            "-y", "-loglevel", "warning",
            saida
        ]
        resultado = subprocess.run(comando, capture_output=True, text=True)
        return resultado.returncode == 0

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = ConversorMP3()
    app.run()
