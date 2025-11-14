import sqlite3
import os
from flask import Flask, render_template, request, redirect, url_for, g, session, flash, abort
import hashlib
from datetime import datetime, timedelta

# --- CONFIGURAÇÃO INICIAL ---
app = Flask(__name__, static_folder='assets', template_folder='.') 
DATABASE = 'zeroday.db'
app.secret_key = 'minha_chave_secreta_super_segura_12345' 

# --- FUNÇÕES DO BANCO DE DADOS (Helpers) ---
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None: db.close()

def hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

# --- FUNÇÃO DE MIGRAÇÃO (Revertida) ---
def setup_database():
    print("Iniciando setup do banco de dados...")
    try:
        with app.app_context():
            db = get_db()
            cursor = db.cursor()
            
            # 1. Tabela 'administradores'
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS administradores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
                    senha_hash TEXT NOT NULL, permissao TEXT NOT NULL
                );
            ''')
            print("Tabela 'administradores' verificada.")
            
            # 2. Tabela 'usuarios'
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS usuarios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
                    discord_user TEXT, senha_hash TEXT NOT NULL
                );
            ''')
            print("Tabela 'usuarios' (base) verificada.")
            
            # 3. Tabela 'pedidos'
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS pedidos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, usuario_id INTEGER NOT NULL, produto_nome TEXT NOT NULL,
                    descricao TEXT NOT NULL, anexos_path TEXT, status_pedido TEXT NOT NULL,
                    status_pagamento TEXT NOT NULL, data_pedido TEXT NOT NULL,
                    FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
                );
            ''')
            print("Tabela 'pedidos' verificada.")
            
            # 4. MIGRAÇÃO: Coluna 'status' em 'usuarios'
            try:
                cursor.execute("ALTER TABLE usuarios ADD COLUMN status TEXT NOT NULL DEFAULT 'Ativo'")
                print("Coluna 'status' adicionada a 'usuarios'.")
            except sqlite3.OperationalError as e:
                if "duplicate column name: status" in str(e):
                    print("Coluna 'status' já existe em 'usuarios'.")
                else: raise e
            
            # 5. MIGRAÇÃO: Coluna 'data_cadastro' em 'usuarios'
            try:
                cursor.execute("ALTER TABLE usuarios ADD COLUMN data_cadastro TEXT")
                print("Coluna 'data_cadastro' adicionada a 'usuarios'.")
            except sqlite3.OperationalError as e:
                if "duplicate column name: data_cadastro" in str(e):
                    print("Coluna 'data_cadastro' já existe em 'usuarios'.")
                else: raise e
            
            # Insere admins (sempre seguro)
            admins = [
                ('Admin Master', 'master@zeroday.com', hash_password("admin123"), 'Super Admin'),
                ('Admin Gestor', 'gestor@zeroday.com', hash_password("admin123"), 'Admin'),
                ('Admin Financeiro', 'financeiro@zeroday.com', hash_password("admin123"), 'Admin (Pagamentos)')
            ]
            cursor.executemany('INSERT OR IGNORE INTO administradores (nome, email, senha_hash, permissao) VALUES (?, ?, ?, ?)', admins)
            
            db.commit()
            print("Banco de dados pronto.")

    except Exception as e:
        print(f"Ocorreu um erro durante o setup: {e}")
        if db: db.rollback()
    finally:
        if db: db.close()

# ==========================================================
# ROTAS DO SITE PRINCIPAL (CLIENTE) (Revertido)
# ==========================================================
@app.route('/')
def home():
    return render_template('index.html', usuario_nome=session.get('usuario_nome'))
@app.route('/produtos')
def produtos():
    return render_template('produtos.html', usuario_nome=session.get('usuario_nome'))

@app.route('/suporte')
def suporte():
    # REVERTIDO: Não busca mais no banco
    return render_template('suporte.html', 
                           usuario_nome=session.get('usuario_nome'))

@app.route('/pagamento')
def pagamento():
    if 'usuario_id' not in session: return redirect(url_for('login'))
    # REVERTIDO: Não busca mais no banco
    return render_template('pagamento.html', 
                           usuario_nome=session.get('usuario_nome'))

@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'POST':
        nome, email, senha = request.form['nome'], request.form['email'], request.form['password']
        if not nome or not email or not senha:
            flash('Todos os campos são obrigatórios.', 'error'); return redirect(url_for('cadastro'))
        senha_hash = hash_password(senha)
        data_atual = datetime.now().strftime("%Y-%m-%d")
        db = get_db()
        try:
            db.execute('INSERT INTO usuarios (nome, email, senha_hash, status, data_cadastro) VALUES (?, ?, ?, ?, ?)', 
                       (nome, email, senha_hash, 'Ativo', data_atual))
            db.commit()
            flash('Conta criada com sucesso! Faça o login.', 'success'); return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Este email já está cadastrado.', 'error'); return redirect(url_for('cadastro'))
    return render_template('cadastro.html', usuario_nome=None)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'usuario_id' in session: return redirect(url_for('painel'))
    if request.method == 'POST':
        email, senha = request.form['email'], request.form['password']
        db = get_db(); usuario = db.execute('SELECT * FROM usuarios WHERE email = ?', (email,)).fetchone()
        if usuario and usuario['senha_hash'] == hash_password(senha):
            if usuario['status'] == 'Bloqueado':
                flash('Esta conta foi suspensa.', 'error'); return redirect(url_for('login'))
            session['usuario_id'], session['usuario_nome'] = usuario['id'], usuario['nome']
            return redirect(url_for('painel'))
        else:
            flash('Email ou senha inválidos.', 'error'); return redirect(url_for('login'))
    return render_template('login.html', usuario_nome=None)

@app.route('/painel')
def painel():
    if 'usuario_id' not in session: return redirect(url_for('login'))
    db = get_db(); usuario_id = session['usuario_id']
    meus_pedidos = db.execute('SELECT * FROM pedidos WHERE usuario_id = ? ORDER BY data_pedido DESC', (usuario_id,)).fetchall()
    meus_dados = db.execute('SELECT nome, email, discord_user FROM usuarios WHERE id = ?', (usuario_id,)).fetchone()
    return render_template('painel.html', usuario_nome=session.get('usuario_nome'), pedidos=meus_pedidos, dados=meus_dados)

@app.route('/logout')
def logout():
    session.pop('usuario_id', None); session.pop('usuario_nome', None)
    return redirect(url_for('home'))

@app.route('/formulario')
def formulario():
    if 'usuario_id' not in session:
        flash('Você precisa estar logado para solicitar um produto.', 'error'); return redirect(url_for('login'))
    produto_escolhido = request.args.get('produto', 'discord')
    return render_template('formulario.html', 
                           produto_escolhido=produto_escolhido, 
                           usuario_nome=session.get('usuario_nome'))

@app.route('/solicitar_pedido', methods=['POST'])
def solicitar_pedido():
    if 'usuario_id' not in session: return redirect(url_for('login'))
    try:
        produto, descricao, discord_user = request.form['produto'], request.form['descricao'], request.form['discord']
        usuario_id = session['usuario_id']; data_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db = get_db()
        db.execute('''
            INSERT INTO pedidos (usuario_id, produto_nome, descricao, status_pedido, status_pagamento, data_pedido, anexos_path)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (usuario_id, produto, descricao, 'Recebido', 'Pendente', data_atual, ''))
        db.execute('UPDATE usuarios SET discord_user = ? WHERE id = ?', (discord_user, usuario_id))
        db.commit()
        return redirect(url_for('pagamento'))
    except Exception as e:
        flash(f'Ocorreu um erro ao enviar seu pedido: {e}', 'error'); return redirect(url_for('formulario'))

# ==========================================================
# ROTAS DO PAINEL ADMIN (Revertido)
# ==========================================================
@app.route('/admin/', methods=['GET', 'POST'])
def admin_login():
    if 'admin_id' in session: return redirect(url_for('admin_dashboard'))
    if request.method == 'POST':
        email, senha = request.form['email'], request.form['password']
        db = get_db(); admin = db.execute('SELECT * FROM administradores WHERE email = ?', (email,)).fetchone()
        if admin and admin['senha_hash'] == hash_password(senha):
            session['admin_id'], session['admin_nome'] = admin['id'], admin['nome']
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Email ou senha inválidos.', 'error'); return redirect(url_for('admin_login'))
    return render_template('admin/index.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    if 'admin_id' not in session: return redirect(url_for('admin_login'))
    db = get_db()
    total_pedidos = db.execute('SELECT COUNT(id) FROM pedidos').fetchone()[0]
    pedidos_pendentes = db.execute("SELECT COUNT(id) FROM pedidos WHERE status_pedido = 'Recebido'").fetchone()[0]
    pagos = db.execute("SELECT COUNT(id) FROM pedidos WHERE status_pagamento = 'Confirmado'").fetchone()[0]
    inicio_do_mes = datetime.now().strftime("%Y-%m-01")
    novos_usuarios = db.execute('SELECT COUNT(id) FROM usuarios WHERE data_cadastro >= ?', (inicio_do_mes,)).fetchone()[0]
    stats = {
        'total_pedidos': total_pedidos, 'pedidos_pendentes': pedidos_pendentes,
        'pagos_confirmados': pagos, 'novos_usuarios': novos_usuarios
    }
    labels_grafico = []; data_grafico = []
    dias_dict = {}
    for i in range(7):
        dia = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        dias_dict[dia] = 0
    sete_dias_atras = (datetime.now() - timedelta(days=6)).strftime("%Y-%m-%d")
    dados_grafico_db = db.execute("SELECT strftime('%Y-%m-%d', data_pedido) as dia, COUNT(id) as contagem FROM pedidos WHERE data_pedido >= ? GROUP BY dia", (sete_dias_atras,)).fetchall()
    for linha in dados_grafico_db:
        if linha['dia'] in dias_dict:
            dias_dict[linha['dia']] = linha['contagem']
    for dia, contagem in sorted(dias_dict.items()):
        labels_grafico.append(dia[5:]); data_grafico.append(contagem)
    return render_template('admin/dashboard.html', 
                           admin_nome=session.get('admin_nome'), stats=stats,
                           labels_grafico=labels_grafico, data_grafico=data_grafico)

@app.route('/admin/pedidos')
def admin_pedidos():
    if 'admin_id' not in session: return redirect(url_for('admin_login'))
    db = get_db()
    lista_de_pedidos = db.execute('SELECT p.*, u.nome as cliente_nome FROM pedidos p JOIN usuarios u ON p.usuario_id = u.id ORDER BY p.data_pedido DESC').fetchall()
    return render_template('admin/pedidos.html', admin_nome=session.get('admin_nome'), pedidos=lista_de_pedidos)

@app.route('/admin/pagamentos')
def admin_pagamentos():
    if 'admin_id' not in session: return redirect(url_for('admin_login'))
    db = get_db()
    lista_de_pagamentos = db.execute("SELECT p.id, p.status_pagamento, u.nome as cliente_nome, p.produto_nome FROM pedidos p JOIN usuarios u ON p.usuario_id = u.id WHERE p.status_pagamento = 'Pendente' ORDER BY p.data_pedido ASC").fetchall()
    return render_template('admin/pagamentos.html', admin_nome=session.get('admin_nome'), pagamentos=lista_de_pagamentos)

@app.route('/admin/usuarios')
def admin_usuarios():
    if 'admin_id' not in session: return redirect(url_for('admin_login'))
    db = get_db()
    lista_de_usuarios = db.execute('SELECT id, nome, email, discord_user, status, data_cadastro FROM usuarios ORDER BY nome').fetchall()
    return render_template('admin/usuarios.html', admin_nome=session.get('admin_nome'), usuarios=lista_de_usuarios)

@app.route('/admin/admins')
def admin_admins():
    if 'admin_id' not in session: return redirect(url_for('admin_login'))
    db = get_db()
    lista_de_admins = db.execute('SELECT id, nome, email, permissao FROM administradores ORDER BY id').fetchall()
    return render_template('admin/admins.html', admin_nome=session.get('admin_nome'), admins=lista_de_admins)

@app.route('/admin/logout')
def admin_logout():
    session.clear(); return redirect(url_for('admin_login'))

# Rota de Configurações (REVERTIDA)
@app.route('/admin/configuracoes')
def admin_configuracoes():
    if 'admin_id' not in session: return redirect(url_for('admin_login'))
    return render_template('admin/configuracoes.html', admin_nome=session.get('admin_nome'))

# Rotas de Ação (Pedidos)
@app.route('/admin/pedido/pagar/<int:id>')
def admin_marcar_pago(id):
    if 'admin_id' not in session: return redirect(url_for('admin_login'))
    db = get_db()
    db.execute("UPDATE pedidos SET status_pagamento = 'Confirmado' WHERE id = ?", (id,))
    db.commit()
    return redirect(request.referrer or url_for('admin_pedidos'))

@app.route('/admin/pedido/status/<int:id>', methods=['POST'])
def admin_atualizar_status(id):
    if 'admin_id' not in session: return redirect(url_for('admin_login'))
    novo_status = request.form['status']
    if novo_status in ['Recebido', 'Em Produção', 'Finalizado', 'Cancelado']:
        db = get_db()
        db.execute("UPDATE pedidos SET status_pedido = ? WHERE id = ?", (novo_status, id))
        db.commit()
    return redirect(url_for('admin_pedidos'))

# Rotas de Ação (Usuários)
@app.route('/admin/usuario/suspender/<int:id>')
def admin_suspender_usuario(id):
    if 'admin_id' not in session: return redirect(url_for('admin_login'))
    db = get_db()
    db.execute("UPDATE usuarios SET status = 'Bloqueado' WHERE id = ?", (id,))
    db.commit()
    return redirect(url_for('admin_usuarios'))

@app.route('/admin/usuario/reativar/<int:id>')
def admin_reativar_usuario(id):
    if 'admin_id' not in session: return redirect(url_for('admin_login'))
    db = get_db()
    db.execute("UPDATE usuarios SET status = 'Ativo' WHERE id = ?", (id,))
    db.commit()
    return redirect(url_for('admin_usuarios'))

@app.route('/admin/usuario/reset/<int:id>', methods=['GET', 'POST'])
def admin_reset_user_password(id):
    if 'admin_id' not in session: return redirect(url_for('admin_login'))
    db = get_db()
    usuario = db.execute('SELECT id, nome, email FROM usuarios WHERE id = ?', (id,)).fetchone()
    if not usuario:
        flash('Usuário não encontrado.', 'error')
        return redirect(url_for('admin_usuarios'))
    if request.method == 'POST':
        nova_senha = request.form['nova_senha']
        confirmar_senha = request.form['confirmar_senha']
        if not nova_senha or not confirmar_senha:
            flash('Por favor, preencha os dois campos.', 'error')
            return redirect(url_for('admin_reset_user_password', id=id))
        if nova_senha != confirmar_senha:
            flash('As senhas não coincidem.', 'error')
            return redirect(url_for('admin_reset_user_password', id=id))
        nova_senha_hash = hash_password(nova_senha)
        db.execute('UPDATE usuarios SET senha_hash = ? WHERE id = ?', (nova_senha_hash, id))
        db.commit()
        flash(f'Senha do usuário {usuario["nome"]} atualizada com sucesso.', 'success')
        return redirect(url_for('admin_usuarios'))
    return render_template('admin/reset_password.html', 
                           admin_nome=session.get('admin_nome'), 
                           usuario=usuario)

# ==========================================================
# ANTI-CACHE
# ==========================================================
@app.after_request
def add_header(response):
    if app.debug:
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response
# ==========================================================
# INICIAR O SERVIDOR
# ==========================================================
if __name__ == '__main__':
    # Este 'setup' é SÓ para testes locais
    setup_database() 
    print("Iniciando o servidor Flask local em http://127.0.0.1:5000/")
    app.run(debug=True, port=5000)