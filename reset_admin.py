import sqlite3
import hashlib

db = sqlite3.connect('data/zeroday.db')

email = 'admin@zeroday.com'
senha = 'admin123'
senha_hash = hashlib.sha256(senha.encode()).hexdigest()

db.execute(
    "UPDATE administradores SET senha_hash = ? WHERE email = ?",
    (senha_hash, email)
)

if db.total_changes == 0:
    db.execute(
        "INSERT INTO administradores (nome, email, senha_hash, permissao) VALUES (?, ?, ?, ?)",
        ("Admin Default", email, senha_hash, "Super Admin")
    )

db.commit()
print("admin pronto:", email, senha)