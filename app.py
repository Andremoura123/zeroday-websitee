import sqlite3
import os
import sys
import uuid
import requests
from requests_oauthlib import OAuth2Session
from flask import Flask, render_template, request, redirect, url_for, g, session, flash, send_from_directory
from werkzeug.utils import secure_filename
import hashlib
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# ==============================================================================
# 1. CONFIGURAÇÕES GERAIS E VARIÁVEIS DE AMBIENTE
# ==============================================================================
DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
DISCORD_GUILD_ID = os.getenv("DISCORD_GUILD_ID")
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

if not FLASK_SECRET_KEY:
    print("AVISO: FLASK_SECRET_KEY não encontrada. Usando chave fallback.")
    FLASK_SECRET_KEY = "fallback-secret-key-123"

RAILWAY_ENVIRONMENT = os.environ.get("RAILWAY_ENVIRONMENT") is not None
FLY_ENVIRONMENT = os.environ.get("FLY_APP_NAME") is not None

IS_PRODUCTION = RAILWAY_ENVIRONMENT or FLY_ENVIRONMENT

if FLY_ENVIRONMENT:
    DISCORD_REDIRECT_URI = "https://SEU-APP.fly.dev/callback"
elif RAILWAY_ENVIRONMENT:
    DISCORD_REDIRECT_URI = "https://SEU-APP.up.railway.app/callback"
else:
    DISCORD_REDIRECT_URI = "http://127.0.0.1:5000/callback"

app = Flask(__name__, static_folder="assets", template_folder=".")
app.secret_key = FLASK_SECRET_KEY
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

if RAILWAY_ENVIRONMENT:
    DATABASE_PATH = "/tmp/zeroday_data"
elif FLY_ENVIRONMENT:
    DATABASE_PATH = "/data"
else:
    DATABASE_PATH = "data"

DATABASE = os.path.join(DATABASE_PATH, "zeroday.db")
UPLOAD_FOLDER = os.path.join(DATABASE_PATH, "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "zip", "rar", "txt", "pdf"}

os.makedirs(DATABASE_PATH, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

AUTHORIZATION_BASE_URL = "https://discord.com/api/oauth2/authorize"
TOKEN_URL = "https://discord.com/api/oauth2/token"
API_BASE_URL = "https://discord.com/api/users/@me"
SCOPES = ["identify", "email", "guilds"]

# ==============================================================================
# 2. FUNÇÕES AUXILIARES
# ==============================================================================

def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        os.makedirs(DATABASE_PATH, exist_ok=True)
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()


def hash_password(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def get_current_user_name():
    return session.get("usuario_nome")


# ==============================================================================
# 3. SETUP DO BANCO
# ==============================================================================

def setup_database():
    print(f"--- INICIANDO SETUP DO BANCO DE DADOS EM: {DATABASE} ---")

    try:
        os.makedirs(DATABASE_PATH, exist_ok=True)
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)

        with app.app_context():
            db = get_db()
            cursor = db.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS administradores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    senha_hash TEXT NOT NULL,
                    permissao TEXT NOT NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS usuarios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    discord_user TEXT,
                    senha_hash TEXT,
                    discord_id TEXT,
                    avatar_hash TEXT,
                    status TEXT DEFAULT 'Ativo',
                    data_cadastro TEXT
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pedidos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usuario_id INTEGER NOT NULL,
                    produto_nome TEXT NOT NULL,
                    descricao TEXT NOT NULL,
                    anexos_path TEXT,
                    status_pedido TEXT NOT NULL,
                    status_pagamento TEXT NOT NULL,
                    data_pedido TEXT NOT NULL,
                    FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS catalogo_itens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    categoria TEXT NOT NULL,
                    nome TEXT NOT NULL,
                    descricao TEXT NOT NULL,
                    icone TEXT
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usuario_id INTEGER,
                    categoria TEXT,
                    assunto TEXT,
                    descricao TEXT,
                    prioridade TEXT,
                    status TEXT,
                    data_criacao TEXT
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ticket_mensagens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket_id INTEGER,
                    remetente_tipo TEXT,
                    remetente_nome TEXT,
                    mensagem TEXT,
                    data_envio TEXT
                )
            """)

            try:
                cursor.execute("ALTER TABLE usuarios ADD COLUMN status TEXT NOT NULL DEFAULT 'Ativo'")
            except Exception:
                pass

            try:
                cursor.execute("ALTER TABLE usuarios ADD COLUMN data_cadastro TEXT")
            except Exception:
                pass

            try:
                cursor.execute("ALTER TABLE usuarios ADD COLUMN discord_id TEXT")
            except Exception:
                pass

            try:
                cursor.execute("ALTER TABLE usuarios ADD COLUMN avatar_hash TEXT")
            except Exception:
                pass

            try:
                cursor.execute("ALTER TABLE usuarios ADD COLUMN discord_user TEXT")
            except Exception:
                pass

            senha_correta_hash = "a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3"  # admin123
            email_admin = "admin@zeroday.com"

            cursor.execute(
                "UPDATE administradores SET senha_hash = ? WHERE email = ?",
                (senha_correta_hash, email_admin)
            )

            if cursor.rowcount == 0:
                cursor.execute(
                    "INSERT INTO administradores (nome, email, senha_hash, permissao) VALUES (?, ?, ?, ?)",
                    ("Admin Default", email_admin, senha_correta_hash, "Super Admin")
                )
                print(">> Admin padrão criado com sucesso.")
            else:
                print(">> Senha do Admin restaurada para o padrão (admin123).")

            db.commit()
            print("--- BANCO DE DADOS PRONTO ---")

    except Exception as e:
        print(f"Erro no setup: {e}")


# ==============================================================================
# 4. FRONTEND
# ==============================================================================

@app.route("/")
def home():
    return render_template("index.html", usuario_nome=get_current_user_name())


@app.route("/produtos")
def produtos():
    return render_template("produtos.html", usuario_nome=get_current_user_name())


@app.route("/catalogo")
def catalogo():
    db = get_db()
    categorias = []

    try:
        categorias_db = db.execute(
            "SELECT DISTINCT categoria FROM catalogo_itens ORDER BY categoria"
        ).fetchall()

        for cat in categorias_db:
            itens = db.execute(
                "SELECT * FROM catalogo_itens WHERE categoria = ? ORDER BY nome",
                (cat["categoria"],)
            ).fetchall()

            categorias.append({
                "nome": cat["categoria"],
                "itens": itens
            })
    except Exception:
        categorias = []

    return render_template(
        "catalogo.html",
        usuario_nome=get_current_user_name(),
        categorias=categorias
    )


@app.route("/formulario/<produto>")
def formulario(produto):
    if "usuario_id" not in session:
        flash("Você precisa estar logado para fazer um pedido.", "error")
        return redirect(url_for("login"))

    return render_template(
        "formulario.html",
        produto_escolhido=produto,
        usuario_nome=get_current_user_name()
    )


@app.route("/termos")
def termos():
    return render_template("termos.html", usuario_nome=get_current_user_name())


@app.route("/privacidade")
def privacidade():
    return render_template("privacidade.html", usuario_nome=get_current_user_name())


@app.route("/pagamento")
def pagamento():
    if "usuario_id" not in session:
        return redirect(url_for("login"))
    return render_template("pagamento.html", usuario_nome=get_current_user_name())


# ==============================================================================
# 5. TICKETS E SUPORTE
# ==============================================================================

@app.route("/tickets")
def tickets():
    return render_template("tickets.html", usuario_nome=get_current_user_name())


@app.route("/suporte")
def suporte():
    return render_template("suporte.html", usuario_nome=get_current_user_name())


@app.route("/novo_ticket/<categoria>")
def novo_ticket(categoria):
    if "usuario_id" not in session:
        flash("Faça login para abrir um ticket.", "error")
        return redirect(url_for("login"))

    return render_template(
        "novo_ticket.html",
        categoria_escolhida=categoria,
        usuario_nome=get_current_user_name()
    )


@app.route("/enviar_ticket", methods=["POST"])
def enviar_ticket():
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    assunto = request.form.get("assunto", "").strip()
    categoria = request.form.get("categoria", "").strip()
    descricao = request.form.get("mensagem", "").strip()
    prioridade = request.form.get("prioridade", "").strip()
    usuario_id = session["usuario_id"]

    if not assunto or not categoria or not descricao:
        flash("Preencha os campos obrigatórios do ticket.", "error")
        return redirect(url_for("tickets"))

    db = get_db()
    data_hoje = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor = db.execute(
        """
        INSERT INTO tickets (usuario_id, categoria, assunto, descricao, prioridade, status, data_criacao)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (usuario_id, categoria, assunto, descricao, prioridade or "Normal", "Pendente", data_hoje)
    )
    ticket_id = cursor.lastrowid

    db.execute(
        """
        INSERT INTO ticket_mensagens (ticket_id, remetente_tipo, remetente_nome, mensagem, data_envio)
        VALUES (?, ?, ?, ?, ?)
        """,
        (ticket_id, "cliente", get_current_user_name(), descricao, data_hoje)
    )
    db.commit()

    if DISCORD_WEBHOOK_URL:
        try:
            requests.post(
                DISCORD_WEBHOOK_URL,
                json={
                    "content": f"🎫 **NOVO TICKET #{ticket_id}**\nUsuário: {get_current_user_name()}\nCategoria: {categoria}\nAssunto: {assunto}"
                },
                timeout=10
            )
        except Exception:
            pass

    flash(f"Ticket #{ticket_id} criado com sucesso! Acompanhe no seu painel.", "success")
    return redirect(url_for("painel", aba="Tickets"))


@app.route("/ver_ticket/<int:ticket_id>")
def ver_ticket(ticket_id):
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    db = get_db()
    ticket = db.execute(
        "SELECT * FROM tickets WHERE id = ? AND usuario_id = ?",
        (ticket_id, session["usuario_id"])
    ).fetchone()

    if not ticket:
        flash("Ticket não encontrado.", "error")
        return redirect(url_for("painel"))

    mensagens = db.execute(
        "SELECT * FROM ticket_mensagens WHERE ticket_id = ? ORDER BY data_envio ASC",
        (ticket_id,)
    ).fetchall()

    return render_template("ticket_chat.html", ticket=ticket, mensagens=mensagens, is_admin=False)


@app.route("/enviar_mensagem_ticket/<int:ticket_id>", methods=["POST"])
def enviar_mensagem_ticket(ticket_id):
    if not session.get("is_admin") and "usuario_id" not in session:
        return redirect(url_for("login"))

    mensagem = request.form.get("mensagem", "").strip()
    if not mensagem:
        flash("Digite uma mensagem.", "error")
        if session.get("is_admin"):
            return redirect(url_for("admin_ver_ticket", ticket_id=ticket_id))
        return redirect(url_for("ver_ticket", ticket_id=ticket_id))

    is_admin = session.get("is_admin", False)
    remetente_tipo = "admin" if is_admin else "cliente"
    remetente_nome = session.get("usuario_nome")
    data_envio = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    db = get_db()
    db.execute(
        """
        INSERT INTO ticket_mensagens (ticket_id, remetente_tipo, remetente_nome, mensagem, data_envio)
        VALUES (?, ?, ?, ?, ?)
        """,
        (ticket_id, remetente_tipo, remetente_nome, mensagem, data_envio)
    )

    if is_admin:
        db.execute("UPDATE tickets SET status = 'Respondido' WHERE id = ?", (ticket_id,))
        db.commit()
        return redirect(url_for("admin_ver_ticket", ticket_id=ticket_id))

    db.commit()
    return redirect(url_for("ver_ticket", ticket_id=ticket_id))


# ==============================================================================
# 6. AUTENTICAÇÃO
# ==============================================================================

def get_discord_auth():
    return OAuth2Session(
        DISCORD_CLIENT_ID,
        redirect_uri=DISCORD_REDIRECT_URI,
        scope=SCOPES
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("is_admin"):
        return redirect(url_for("admin_dashboard"))

    if "usuario_id" in session:
        return redirect(url_for("painel"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")

        db = get_db()

        # tenta login como admin primeiro
        admin_user = db.execute(
            "SELECT * FROM administradores WHERE lower(email) = ?",
            (email,)
        ).fetchone()

        if admin_user and hash_password(senha) == admin_user["senha_hash"]:
            session.clear()
            session["admin_id"] = admin_user["id"]
            session["usuario_nome"] = admin_user["nome"]
            session["is_admin"] = True
            flash("Login administrativo realizado com sucesso.", "success")
            return redirect(url_for("admin_dashboard"))

        # se não for admin, tenta login de usuário normal
        usuario = db.execute(
            "SELECT * FROM usuarios WHERE lower(email) = ?",
            (email,)
        ).fetchone()

        if usuario and usuario["senha_hash"] and hash_password(senha) == usuario["senha_hash"]:
            session.clear()
            session["usuario_id"] = usuario["id"]
            session["usuario_nome"] = usuario["nome"]
            session["is_admin"] = False
            flash("Login realizado com sucesso.", "success")
            return redirect(url_for("painel"))

        flash("Email ou senha incorretos.", "error")
        return redirect(url_for("login"))

    discord_url = "#"
    if DISCORD_CLIENT_ID and DISCORD_CLIENT_SECRET:
        try:
            discord = get_discord_auth()
            authorization_url, state = discord.authorization_url(AUTHORIZATION_BASE_URL)
            session["oauth_state"] = state
            discord_url = authorization_url
        except Exception:
            discord_url = "#"

    return render_template("login.html", discord_url=discord_url)


@app.route("/callback")
def callback():
    if request.args.get("error"):
        return redirect(url_for("login"))

    if "oauth_state" not in session or session["oauth_state"] != request.args.get("state"):
        return redirect(url_for("login"))

    discord = get_discord_auth()

    try:
        token = discord.fetch_token(
            TOKEN_URL,
            client_secret=DISCORD_CLIENT_SECRET,
            authorization_response=request.url
        )
    except Exception:
        flash("Não foi possível concluir o login com Discord.", "error")
        return redirect(url_for("login"))

    session["oauth_token"] = token
    user_data = discord.get(API_BASE_URL).json()

    try:
        guilds = discord.get("https://discord.com/api/users/@me/guilds").json()
        if isinstance(guilds, list) and DISCORD_GUILD_ID:
            is_member = any(guild["id"] == DISCORD_GUILD_ID for guild in guilds)
            if not is_member:
                flash("Você precisa ser membro do nosso Discord.", "error")
                return redirect(url_for("login"))
    except Exception:
        pass

    db = get_db()
    discord_id = user_data["id"]
    email = user_data.get("email", f"{discord_id}@discord.local")
    usuario_db = db.execute(
        "SELECT * FROM usuarios WHERE discord_id = ? OR email = ?",
        (discord_id, email)
    ).fetchone()

    if usuario_db:
        session["usuario_id"] = usuario_db["id"]
        session["usuario_nome"] = usuario_db["nome"]
        session["is_admin"] = False

        db.execute(
            "UPDATE usuarios SET discord_user = ?, avatar_hash = ? WHERE id = ?",
            (user_data.get("username"), user_data.get("avatar"), usuario_db["id"])
        )
        db.commit()
    else:
        nome = user_data.get("global_name") or user_data.get("username") or "Usuário Discord"
        db.execute(
            """
            INSERT INTO usuarios (nome, email, discord_user, discord_id, avatar_hash, status, data_cadastro)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                nome,
                email,
                user_data.get("username"),
                discord_id,
                user_data.get("avatar"),
                "Ativo",
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
        )
        db.commit()

        novo_usuario = db.execute(
            "SELECT * FROM usuarios WHERE discord_id = ?",
            (discord_id,)
        ).fetchone()

        session["usuario_id"] = novo_usuario["id"]
        session["usuario_nome"] = nome
        session["is_admin"] = False

    return redirect(url_for("painel"))


@app.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    if request.method == "GET":
        return render_template("cadastro.html", usuario_nome=get_current_user_name())

    nome = request.form.get("nome", "").strip()
    email = request.form.get("email", "").strip().lower()
    discord_user = request.form.get("discord", "").strip()
    senha = request.form.get("senha", "")
    confirmar_senha = request.form.get("confirmar_senha", "")

    if not nome or not email or not senha:
        flash("Preencha todos os campos obrigatórios.", "error")
        return redirect(url_for("cadastro"))

    if senha != confirmar_senha:
        flash("As senhas não conferem.", "error")
        return redirect(url_for("cadastro"))

    db = get_db()

    if db.execute("SELECT id FROM usuarios WHERE lower(email) = ?", (email,)).fetchone():
        flash("Este e-mail já está em uso.", "error")
        return redirect(url_for("cadastro"))

    try:
        db.execute(
            """
            INSERT INTO usuarios (nome, email, discord_user, senha_hash, status, data_cadastro)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                nome,
                email,
                discord_user or None,
                hash_password(senha),
                "Ativo",
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
        )
        db.commit()
        flash("Cadastro realizado com sucesso. Agora faça login.", "success")
        return redirect(url_for("login"))
    except Exception:
        flash("Erro ao cadastrar usuário.", "error")
        return redirect(url_for("cadastro"))


@app.route("/painel")
def painel():
    if session.get("is_admin"):
        return redirect(url_for("admin_dashboard"))

    if "usuario_id" not in session:
        return redirect(url_for("login"))

    db = get_db()
    usuario_id = session["usuario_id"]

    usuario = db.execute(
        "SELECT * FROM usuarios WHERE id = ?",
        (usuario_id,)
    ).fetchone()

    pedidos = db.execute(
        "SELECT * FROM pedidos WHERE usuario_id = ? ORDER BY data_pedido DESC",
        (usuario_id,)
    ).fetchall()

    tickets = db.execute(
        "SELECT * FROM tickets WHERE usuario_id = ? ORDER BY data_criacao DESC",
        (usuario_id,)
    ).fetchall()

    return render_template(
        "painel.html",
        usuario=usuario,
        dados=usuario,
        pedidos=pedidos,
        tickets=tickets,
        usuario_nome=get_current_user_name()
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


# ==============================================================================
# 7. PEDIDOS
# ==============================================================================

@app.route("/solicitar_pedido", methods=["POST"])
def solicitar_pedido():
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    produto = request.form.get("produto", "").strip()
    descricao = request.form.get("descricao", "").strip()
    anexos = request.files.getlist("anexos")
    usuario_id = session["usuario_id"]

    if not produto or not descricao:
        flash("Preencha produto e descrição.", "error")
        return redirect(url_for("painel"))

    anexos_path = None
    if anexos and any(file.filename for file in anexos):
        try:
            pedido_uuid = str(uuid.uuid4())
            pedido_dir = os.path.join(UPLOAD_FOLDER, pedido_uuid)
            os.makedirs(pedido_dir, exist_ok=True)

            for file in anexos:
                if file and file.filename and allowed_file(file.filename):
                    file.save(os.path.join(pedido_dir, secure_filename(file.filename)))

            anexos_path = pedido_uuid
        except Exception:
            pass

    db = get_db()
    db.execute(
        """
        INSERT INTO pedidos (usuario_id, produto_nome, descricao, anexos_path, status_pedido, status_pagamento, data_pedido)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            usuario_id,
            produto,
            descricao,
            anexos_path,
            "Pendente",
            "Aguardando",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
    )
    db.commit()

    if DISCORD_WEBHOOK_URL:
        try:
            requests.post(
                DISCORD_WEBHOOK_URL,
                json={"content": f"🚨 **NOVO PEDIDO**\nProduto: {produto}"},
                timeout=10
            )
        except Exception:
            pass

    flash("Pedido realizado! Por favor, efetue o pagamento.", "success")
    return redirect(url_for("pagamento"))


@app.route("/download_anexo/<pedido_path>/<filename>")
def download_anexo(pedido_path, filename):
    if "usuario_id" not in session and not session.get("is_admin"):
        return redirect(url_for("login"))

    return send_from_directory(
        os.path.join(UPLOAD_FOLDER, pedido_path),
        filename,
        as_attachment=True
    )


# ==============================================================================
# 8. ADMIN
# ==============================================================================

def admin_required(f):
    def wrapper(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper


@app.route("/gerenciamento")
def admin_login():
    if session.get("is_admin"):
        return redirect(url_for("admin_dashboard"))
    return render_template("admin_login.html")


@app.route("/admin_login_post", methods=["POST"])
def admin_login_post():
    email = request.form.get("email", "").strip().lower()
    senha = request.form.get("senha", "")

    db = get_db()
    admin_user = db.execute(
        "SELECT * FROM administradores WHERE lower(email) = ?",
        (email,)
    ).fetchone()

    if admin_user and hash_password(senha) == admin_user["senha_hash"]:
        session["admin_id"] = admin_user["id"]
        session["usuario_nome"] = admin_user["nome"]
        session["is_admin"] = True
        return redirect(url_for("admin_dashboard"))

    flash("Credenciais inválidas.", "error")
    return redirect(url_for("admin_login"))


@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    db = get_db()

    try:
        total = db.execute("SELECT COUNT(id) FROM pedidos").fetchone()[0]
        pendentes = db.execute("SELECT COUNT(id) FROM pedidos WHERE status_pedido = 'Pendente'").fetchone()[0]
        pagos = db.execute("SELECT COUNT(id) FROM pedidos WHERE status_pagamento = 'Confirmado'").fetchone()[0]
        tickets_abertos = db.execute("SELECT COUNT(id) FROM tickets WHERE status != 'Concluido'").fetchone()[0]

        stats = {
            "total_pedidos": total,
            "pedidos_pendentes": pendentes,
            "pagos_confirmados": pagos,
            "tickets_abertos": tickets_abertos
        }
    except Exception:
        stats = {
            "total_pedidos": 0,
            "pedidos_pendentes": 0,
            "pagos_confirmados": 0,
            "tickets_abertos": 0
        }

    labels_grafico = [(datetime.now() - timedelta(days=i)).strftime("%d/%m") for i in range(6, -1, -1)]
    dados_grafico = [0, 0, 0, 0, 0, 0, stats["total_pedidos"]]

    return render_template(
        "admin/dashboard.html",
        stats=stats,
        labels_grafico=labels_grafico,
        dados_grafico=dados_grafico,
        usuario_nome=session.get("usuario_nome")
    )


@app.route("/admin/pedidos")
@admin_required
def admin_pedidos():
    db = get_db()
    pedidos = db.execute("""
        SELECT p.*, u.nome AS usuario_nome, u.email AS usuario_email
        FROM pedidos p
        JOIN usuarios u ON p.usuario_id = u.id
        ORDER BY p.data_pedido DESC
    """).fetchall()

    return render_template("admin/pedidos.html", pedidos=pedidos, admin_nome=session.get("usuario_nome"))


@app.route("/admin/pedidos/update/<int:pedido_id>", methods=["POST"])
@admin_required
def admin_update_pedido(pedido_id):
    db = get_db()
    db.execute(
        "UPDATE pedidos SET status_pedido = ?, status_pagamento = ? WHERE id = ?",
        (
            request.form.get("status_pedido"),
            request.form.get("status_pagamento"),
            pedido_id
        )
    )
    db.commit()
    return redirect(url_for("admin_pedidos"))


@app.route("/admin/tickets")
@admin_required
def admin_tickets():
    db = get_db()
    tickets = db.execute("""
        SELECT t.*, u.nome as usuario_nome, u.email as usuario_email
        FROM tickets t
        JOIN usuarios u ON t.usuario_id = u.id
        ORDER BY t.data_criacao DESC
    """).fetchall()

    return render_template("admin_tickets.html", tickets=tickets, admin_nome=session.get("usuario_nome"))


@app.route("/admin/ver_ticket/<int:ticket_id>")
@admin_required
def admin_ver_ticket(ticket_id):
    db = get_db()
    ticket = db.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    mensagens = db.execute(
        "SELECT * FROM ticket_mensagens WHERE ticket_id = ? ORDER BY data_envio ASC",
        (ticket_id,)
    ).fetchall()

    return render_template("ticket_chat.html", ticket=ticket, mensagens=mensagens, is_admin=True)


@app.route("/admin/fechar_ticket/<int:ticket_id>")
@admin_required
def admin_fechar_ticket(ticket_id):
    db = get_db()
    db.execute("UPDATE tickets SET status = 'Concluido' WHERE id = ?", (ticket_id,))
    db.commit()
    return redirect(url_for("admin_tickets"))


@app.route("/admin/catalogo")
@admin_required
def admin_catalogo():
    db = get_db()
    itens = db.execute("SELECT * FROM catalogo_itens ORDER BY categoria, nome").fetchall()
    return render_template("admin/catalogo.html", itens=itens, admin_nome=session.get("usuario_nome"))


@app.route("/admin/catalogo/adicionar", methods=["POST"])
@admin_required
def admin_adicionar_item():
    nome = request.form.get("nome", "").strip()
    categoria = request.form.get("categoria", "").strip()
    descricao = request.form.get("descricao", "").strip()
    icone = request.form.get("icone", "").strip() or "fas fa-box"

    db = get_db()
    db.execute(
        "INSERT INTO catalogo_itens (categoria, nome, descricao, icone) VALUES (?, ?, ?, ?)",
        (categoria, nome, descricao, icone)
    )
    db.commit()
    flash("Item adicionado.", "success")
    return redirect(url_for("admin_catalogo"))


@app.route("/admin/catalogo/deletar/<int:item_id>")
@admin_required
def admin_deletar_item(item_id):
    db = get_db()
    db.execute("DELETE FROM catalogo_itens WHERE id = ?", (item_id,))
    db.commit()
    flash("Item removido.", "success")
    return redirect(url_for("admin_catalogo"))


@app.route("/admin/admins")
@admin_required
def admin_admins():
    db = get_db()
    admins = db.execute("SELECT * FROM administradores ORDER BY id").fetchall()
    return render_template("admin/admins.html", admins=admins, admin_nome=session.get("usuario_nome"))


@app.route("/admin/admins/adicionar", methods=["POST"])
@admin_required
def admin_adicionar_admin():
    nome = request.form.get("nome", "").strip()
    email = request.form.get("email", "").strip().lower()
    senha = request.form.get("senha", "")

    db = get_db()
    if db.execute("SELECT id FROM administradores WHERE lower(email) = ?", (email,)).fetchone():
        flash("Email já existe.", "error")
        return redirect(url_for("admin_admins"))

    db.execute(
        "INSERT INTO administradores (nome, email, senha_hash, permissao) VALUES (?, ?, ?, ?)",
        (nome, email, hash_password(senha), "Admin")
    )
    db.commit()
    flash("Admin adicionado.", "success")
    return redirect(url_for("admin_admins"))


@app.route("/admin/admins/deletar/<int:admin_id>")
@admin_required
def admin_deletar_admin(admin_id):
    if admin_id == session.get("admin_id"):
        flash("Não pode se deletar.", "error")
        return redirect(url_for("admin_admins"))

    db = get_db()
    db.execute("DELETE FROM administradores WHERE id = ?", (admin_id,))
    db.commit()
    flash("Admin removido.", "success")
    return redirect(url_for("admin_admins"))


@app.route("/admin/usuarios")
@admin_required
def admin_usuarios():
    db = get_db()
    usuarios = db.execute("SELECT * FROM usuarios ORDER BY data_cadastro DESC").fetchall()
    return render_template("admin/usuarios.html", usuarios=usuarios, admin_nome=session.get("usuario_nome"))


@app.route("/admin/pagamentos")
@admin_required
def admin_pagamentos():
    return render_template("admin/pagamentos.html", admin_nome=session.get("usuario_nome"))


@app.route("/admin/configuracoes")
@admin_required
def admin_configuracoes():
    return render_template("admin/configuracoes.html", admin_nome=session.get("usuario_nome"))


@app.route("/admin_logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


# ==============================================================================
# 9. FINAL
# ==============================================================================

@app.after_request
def add_header(response):
    if app.debug:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "setup":
        setup_database()
    else:
        app.run(debug=True, port=5000)