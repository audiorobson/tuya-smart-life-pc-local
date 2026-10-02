"""Interface Tkinter; a thread principal nunca executa operações de rede."""
import copy
import json
import queue
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from tkinter import filedialog, messagebox, ttk

from .config import KINDS, import_devices, load, merge_discovery, pending, save, validate
from .service import LocalHub, discover


class App:
    def __init__(self, root, path):
        self.root, self.path = root, path
        self.config = load(path)
        self.hub = LocalHub(self.config)
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.results = queue.Queue()
        self.busy = False
        self.closed = False
        self.last_states = {}
        root.title("Tuya Local — dispositivos, gateways e painéis")
        root.geometry("1100x700")
        root.minsize(800, 500)
        root.protocol("WM_DELETE_WINDOW", self.close)
        toolbar = ttk.Frame(root, padding=10)
        toolbar.pack(fill="x")
        self.buttons = []
        for text, callback in [("Descobrir na rede", self.scan), ("Importar devices.json", self.import_file),
                               ("Adicionar", self.add), ("Editar", self.edit), ("Consultar selecionado", self.refresh)]:
            button = ttk.Button(toolbar, text=text, command=callback)
            button.pack(side="left", padx=3)
            self.buttons.append(button)
        self.monitor = tk.BooleanVar(value=False)
        ttk.Checkbutton(toolbar, text="Escutar gateways", variable=self.monitor).pack(side="left", padx=8)
        self.tree = ttk.Treeview(root, columns=("kind", "ip", "version", "state", "seen"), selectmode="browse")
        self.tree.heading("#0", text="Dispositivo / gateway")
        self.tree.column("#0", width=260)
        for key, label, width in [("kind", "Tipo", 80), ("ip", "IP", 115), ("version", "Protocolo", 65),
                                  ("state", "Situação", 240), ("seen", "Última leitura (UTC)", 170)]:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width)
        self.tree.pack(fill="both", expand=True, padx=10)
        self.tree.bind("<<TreeviewSelect>>", lambda event: self.show_details())
        self.actions = ttk.Frame(root, padding=10)
        self.actions.pack(fill="x")
        self.details = tk.Text(root, height=9, wrap="word", state="disabled")
        self.details.pack(fill="x", padx=10)
        self.message = tk.StringVar(value="Descubra equipamentos ou importe o cadastro. Nenhum comando é enviado automaticamente.")
        ttk.Label(root, textvariable=self.message, padding=10, wraplength=1050).pack(fill="x")
        self.render()
        root.after(100, self.drain)
        root.after(1500, self.tick)

    def selected(self):
        selection = self.tree.selection()
        return selection[0] if selection else None

    def set_busy(self, value):
        self.busy = value
        for button in self.buttons:
            button.configure(state="disabled" if value else "normal")
        for child in self.actions.winfo_children():
            if isinstance(child, ttk.Button):
                child.configure(state="disabled" if value else "normal")

    def submit(self, work, done, message=None):
        if self.busy or self.closed:
            return
        self.set_busy(True)
        if message:
            self.message.set(message)
        future = self.executor.submit(work)
        future.add_done_callback(lambda f: self.results.put((f, done)))

    def drain(self):
        if self.closed:
            return
        try:
            future, callback = self.results.get_nowait()
        except queue.Empty:
            pass
        else:
            self.set_busy(False)
            try:
                callback(future.result())
            except Exception as exc:
                # Não mostrar exceções de rede contendo payloads ou credenciais.
                text = str(exc) if type(exc) is ValueError else "Operação falhou. Verifique arquivo, configuração e conexão."
                self.message.set(text)
                messagebox.showerror("Tuya Local", text, parent=self.root)
        self.root.after(100, self.drain)

    def install_config(self, config):
        save(config, self.path)
        old = self.hub
        self.hub = LocalHub(config)
        self.config = config
        self.last_states = {}
        self.submit(old.close, lambda _: None)
        self.render()
        self.message.set("Cadastro salvo localmente. Equipamentos sem chave permanecem pendentes.")

    def scan(self):
        self.submit(lambda: merge_discovery(self.config, discover(20)), self.install_config,
                    "Buscando anúncios Tuya por 20 segundos…")

    def import_file(self):
        path = filedialog.askopenfilename(parent=self.root, title="Selecione devices.json do TinyTuya",
                                          filetypes=[("JSON", "*.json")])
        if not path:
            return
        def work():
            with open(path, encoding="utf-8-sig") as stream:
                source = json.load(stream)
            return import_devices(self.config, source)
        self.submit(work, self.install_config, "Importando cadastro…")

    def render(self):
        selected = self.selected()
        self.tree.delete(*self.tree.get_children())
        by_id = {d["id"]: d for d in self.config["devices"]}
        # Pais primeiro; cadastro validado impede ciclos e múltiplos níveis.
        for d in sorted(self.config["devices"], key=lambda item: bool(item.get("parent"))):
            state = self.last_states.get(d["id"], {})
            readiness = pending(d, by_id)
            label = state.get("detail") or state.get("state") or readiness or "Pronto para testar"
            self.tree.insert(d.get("parent", ""), "end", iid=d["id"], text=d.get("name", d["id"]), open=True,
                             values=(d.get("kind", "wifi"), d.get("ip", "Via gateway"),
                                     d.get("version", ""), label, state.get("last_seen") or "—"))
        if selected and selected in by_id:
            self.tree.selection_set(selected)
        self.show_details()

    def show_details(self):
        for child in self.actions.winfo_children():
            child.destroy()
        device_id = self.selected()
        text = "Selecione um equipamento. A descoberta não determina seu tipo: identifique gateways e painéis em Editar."
        if device_id:
            entry = next(d for d in self.config["devices"] if d["id"] == device_id)
            state = self.last_states.get(device_id, {})
            text = json.dumps({"id": device_id, "room": entry.get("room", ""),
                               "parent": entry.get("parent", ""), "node_id": entry.get("node_id", ""),
                               "state": state}, ensure_ascii=False, indent=2)
            for index, control in enumerate(entry.get("controls", [])):
                for action in control["values"]:
                    button = ttk.Button(self.actions, text=f"{control.get('name', control['dp'])}: {action}",
                                        command=lambda i=index, a=action: self.act(i, a))
                    button.pack(side="left", padx=3)
                    if self.busy:
                        button.configure(state="disabled")
            if not entry.get("controls"):
                ttk.Label(self.actions, text="Somente leitura. Cadastre canais e ações em Editar para habilitar controles.").pack(anchor="w")
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", text)
        self.details.configure(state="disabled")

    def receive_states(self, states):
        for state in states:
            self.last_states[state["id"]] = state
        self.render()

    def refresh(self):
        device_id = self.selected()
        if device_id:
            def done(state):
                self.receive_states([state])
                self.message.set("Consulta concluída. Leituras anteriores são preservadas com sua data.")
            self.submit(lambda: self.hub.status(device_id), done, "Consultando estado…")

    def act(self, index, action):
        device_id = self.selected()
        if self.busy or not device_id:
            return
        entry = self.hub.devices[device_id]
        if not messagebox.askyesno("Confirmar acionamento", f"Executar '{action}' em {entry.get('name', device_id)}?", parent=self.root):
            return
        def done(state):
            self.receive_states([state])
            self.message.set("Estado solicitado confirmado." if state["command_confirmed"] else
                             "Comando enviado, mas estado final não confirmado. Verifique o equipamento antes de repetir.")
        self.submit(lambda: self.hub.command(device_id, index, action), done, "Enviando comando e verificando estado…")

    def tick(self):
        if self.closed:
            return
        if self.monitor.get() and not self.busy:
            self.submit(self.hub.events, self.receive_states)
        self.root.after(1500, self.tick)

    def add(self):
        self.edit(new=True)

    def edit(self, new=False):
        if self.busy:
            return
        device_id = None if new else self.selected()
        if not new and not device_id:
            return
        original = {} if new else next(d for d in self.config["devices"] if d["id"] == device_id)
        dialog = tk.Toplevel(self.root)
        dialog.title("Cadastro do equipamento")
        dialog.transient(self.root)
        dialog.grab_set()
        self.monitor.set(False)
        fields = {}
        labels = [("id", "ID"), ("name", "Nome"), ("kind", "Tipo"), ("room", "Ambiente"),
                  ("ip", "IP (conexão direta)"), ("version", "Protocolo (3.1 a 3.5)"),
                  ("key", "Chave local"), ("parent", "ID do gateway/painel pai"), ("node_id", "node_id / cid (Zigbee)")]
        for row, (field, label) in enumerate(labels):
            ttk.Label(dialog, text=label).grid(row=row, column=0, sticky="w", padx=10, pady=4)
            var = tk.StringVar(value=str(original.get(field, "wifi" if field == "kind" else "")))
            fields[field] = var
            if field == "kind":
                widget = ttk.Combobox(dialog, textvariable=var, values=KINDS, state="readonly", width=45)
            else:
                widget = ttk.Entry(dialog, textvariable=var, width=48, show="•" if field == "key" else "")
                if field == "id" and not new:
                    widget.configure(state="readonly")
            widget.grid(row=row, column=1, padx=10, pady=4)
        ttk.Label(dialog, text='Controles JSON: [{"name":"Luz", "dp":"1", "values":{"Ligar":true,"Desligar":false}}]',
                  wraplength=600).grid(row=9, column=0, columnspan=2, padx=10, pady=8)
        controls = tk.Text(dialog, width=75, height=7)
        controls.insert("1.0", json.dumps(original.get("controls", []), ensure_ascii=False, indent=2))
        controls.grid(row=10, column=0, columnspan=2, padx=10)
        ttk.Label(dialog, text="Use apenas canais e valores confirmados para este modelo. Deixe [] para somente leitura.",
                  wraplength=600).grid(row=11, column=0, columnspan=2, padx=10, pady=8)
        def commit():
            try:
                entry = {field: var.get().strip() for field, var in fields.items() if var.get().strip()}
                entry["controls"] = json.loads(controls.get("1.0", "end"))
                config = copy.deepcopy(self.config)
                if new:
                    config["devices"].append(entry)
                else:
                    config["devices"] = [entry if d["id"] == device_id else d for d in config["devices"]]
                validate(config)
                self.install_config(config)
                dialog.destroy()
            except (ValueError, OSError) as exc:
                text = "JSON dos controles inválido." if isinstance(exc, json.JSONDecodeError) else str(exc)
                messagebox.showerror("Cadastro inválido", text, parent=dialog)
        ttk.Button(dialog, text="Salvar", command=commit).grid(row=12, column=1, sticky="e", padx=10, pady=10)

    def close(self):
        self.closed = True
        self.executor.submit(self.hub.close)
        self.executor.shutdown(wait=False, cancel_futures=False)
        self.root.destroy()


def run(path):
    root = tk.Tk()
    App(root, path)
    root.mainloop()
