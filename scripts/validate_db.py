#!/usr/bin/env python3
"""
validate_db.py — Script de Validação do Banco de Dados MySQL
=============================================================
Executa duas verificações críticas antes de subir a aplicação:

  1. Testa a conexão com o MySQL
  2. Verifica se a tabela `leads` existe. Se não existir, cria automaticamente.

Uso:
  python scripts/validate_db.py
  python scripts/validate_db.py --create-only
  python scripts/validate_db.py --check-only

Variáveis de ambiente (lidas do .env na raiz do projeto):
  DATABASE_URL=mysql+aiomysql://vigil:vigil123@localhost:3306/vigildb
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Garante que o script encontra o .env na raiz do projeto
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "vigil_agent"))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT_DIR / ".env")
except ImportError:
    pass  # python-dotenv não instalado; lê as variáveis diretamente do ambiente

import aiomysql

# ── Configuração ──────────────────────────────────────────────────────────────

def _parse_mysql_url(url: str) -> dict:
    """
    Extrai host, port, user, password e database de uma DATABASE_URL no formato:
      mysql+aiomysql://user:password@host:port/database
    """
    # Remove o prefixo do driver
    url = url.replace("mysql+aiomysql://", "").replace("mysql://", "")

    # user:password@host:port/db
    credentials, rest = url.split("@", 1)
    user, password = credentials.split(":", 1)

    host_port, database = rest.split("/", 1)
    if ":" in host_port:
        host, port = host_port.split(":", 1)
        port = int(port)
    else:
        host = host_port
        port = 3306

    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "db": database,
    }


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "mysql+aiomysql://vigil:vigil123@localhost:3306/vigildb",
)

DB_PARAMS = _parse_mysql_url(DATABASE_URL)

# ── DDL da tabela `leads` ─────────────────────────────────────────────────────

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS leads (
    -- Identidade
    id              INT             NOT NULL AUTO_INCREMENT,
    name            VARCHAR(255)    NOT NULL,
    email           VARCHAR(255)    NOT NULL UNIQUE,
    phone           VARCHAR(50)     NULL,

    -- Contexto profissional
    company         VARCHAR(255)    NULL,
    role            VARCHAR(255)    NULL,
    company_size    VARCHAR(50)     NULL,
    sector          VARCHAR(100)    NULL,
    linkedin_url    VARCHAR(500)    NULL,

    -- Enriquecimento
    enrichment_data     JSON        NULL COMMENT 'Dados enriquecidos (cargo, setor, interesses)',
    qualification_score FLOAT       NULL COMMENT 'Score ICP de 0.0 a 1.0',

    -- Estado do funil
    status          ENUM(
                        'new', 'enriched', 'contacted', 'confirmed',
                        'declined', 'no_response', 'attended', 'no_show',
                        'followed_up', 'meeting_booked', 'out_of_icp'
                    ) NOT NULL DEFAULT 'new',
    funnel_phase    ENUM(
                        'capture', 'enrichment', 'pre_event', 'post_event', 'closed'
                    ) NOT NULL DEFAULT 'capture',

    -- Histórico de comunicação
    communication_log   JSON        NULL COMMENT 'Log de mensagens enviadas e recebidas',
    last_contacted_at   DATETIME    NULL,
    contact_attempts    INT         NOT NULL DEFAULT 0,

    -- Contexto pós-evento
    event_notes     TEXT            NULL COMMENT 'Anotações capturadas durante o evento',
    attended        TINYINT(1)      NULL COMMENT '1=compareceu, 0=não compareceu',

    -- LGPD
    lgpd_consent    TINYINT(1)      NOT NULL DEFAULT 0,
    consent_at      DATETIME        NULL,

    -- Timestamps
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    INDEX idx_email         (email),
    INDEX idx_status        (status),
    INDEX idx_funnel_phase  (funnel_phase),
    INDEX idx_created_at    (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Leads do evento Vigil Summit — ciclo de vida completo do funil';
"""


# ── 1. Teste de Conexão ───────────────────────────────────────────────────────

async def check_connection() -> bool:
    """Verifica se o MySQL está acessível com as credenciais configuradas."""
    print("\n" + "=" * 60)
    print("  VERIFICAÇÃO 1 — Conexão com o MySQL")
    print("=" * 60)
    print(f"  Host     : {DB_PARAMS['host']}:{DB_PARAMS['port']}")
    print(f"  Database : {DB_PARAMS['db']}")
    print(f"  Usuário  : {DB_PARAMS['user']}")
    print("-" * 60)

    try:
        conn = await aiomysql.connect(
            host=DB_PARAMS["host"],
            port=DB_PARAMS["port"],
            user=DB_PARAMS["user"],
            password=DB_PARAMS["password"],
            db=DB_PARAMS["db"],
            connect_timeout=5,
        )
        async with conn.cursor() as cur:
            await cur.execute("SELECT VERSION()")
            version = (await cur.fetchone())[0]

        conn.close()
        print(f"  ✅ Conexão estabelecida com sucesso!")
        print(f"  📌 Versão do MySQL: {version}")
        return True

    except aiomysql.OperationalError as e:
        errno, msg = e.args
        print(f"  ❌ Falha na conexão!")
        print(f"  Erro [{errno}]: {msg}")
        print()
        if errno == 1045:
            print("  💡 Dica: Verifique usuário/senha no seu .env")
        elif errno == 2003:
            print("  💡 Dica: MySQL não está rodando. Execute: docker compose up -d")
        elif errno == 1049:
            print(f"  💡 Dica: O banco '{DB_PARAMS['db']}' não existe. Crie-o primeiro.")
        return False

    except Exception as e:
        print(f"  ❌ Erro inesperado: {type(e).__name__}: {e}")
        return False


# ── 2. Verificação e Criação da Tabela ────────────────────────────────────────

async def check_and_create_table() -> bool:
    """
    Verifica se a tabela `leads` existe.
    Se não existir, cria automaticamente com todos os campos necessários.
    """
    print("\n" + "=" * 60)
    print("  VERIFICAÇÃO 2 — Tabela `leads`")
    print("=" * 60)

    try:
        conn = await aiomysql.connect(
            host=DB_PARAMS["host"],
            port=DB_PARAMS["port"],
            user=DB_PARAMS["user"],
            password=DB_PARAMS["password"],
            db=DB_PARAMS["db"],
            connect_timeout=5,
        )

        async with conn.cursor() as cur:
            # Verifica se a tabela existe
            await cur.execute(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = %s AND table_name = 'leads'",
                (DB_PARAMS["db"],),
            )
            exists = (await cur.fetchone())[0] > 0

            if exists:
                # Tabela existe — verifica as colunas
                print("  ✅ Tabela `leads` já existe!")
                await cur.execute("DESCRIBE leads")
                columns = await cur.fetchall()
                print(f"  📋 Colunas encontradas ({len(columns)}):")
                for col in columns:
                    col_name, col_type, nullable, key, default, extra = col
                    key_info = f" [{key}]" if key else ""
                    print(f"     • {col_name:<25} {col_type}{key_info}")

                # Conta registros existentes
                await cur.execute("SELECT COUNT(*) FROM leads")
                total = (await cur.fetchone())[0]
                print(f"\n  📊 Registros na tabela: {total}")

            else:
                # Tabela não existe — cria agora
                print("  ⚠️  Tabela `leads` NÃO encontrada.")
                print("  🔧 Criando tabela com todos os campos...")
                print()

                await cur.execute(CREATE_TABLE_SQL)
                await conn.commit()

                # Confirma criação
                await cur.execute(
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_schema = %s AND table_name = 'leads'",
                    (DB_PARAMS["db"],),
                )
                created = (await cur.fetchone())[0] > 0

                if created:
                    print("  ✅ Tabela `leads` criada com sucesso!")
                    await cur.execute("DESCRIBE leads")
                    columns = await cur.fetchall()
                    print(f"  📋 Colunas criadas ({len(columns)}):")
                    for col in columns:
                        col_name, col_type, nullable, key, default, extra = col
                        key_info = f" [{key}]" if key else ""
                        print(f"     • {col_name:<25} {col_type}{key_info}")
                else:
                    print("  ❌ Falha ao criar a tabela. Verifique as permissões do usuário MySQL.")
                    conn.close()
                    return False

        conn.close()
        return True

    except aiomysql.OperationalError as e:
        errno, msg = e.args
        print(f"  ❌ Erro de operação [{errno}]: {msg}")
        if errno == 1142:
            print("  💡 Dica: O usuário não tem permissão para criar tabelas.")
            print(f"  Execute como root: GRANT ALL ON {DB_PARAMS['db']}.* TO '{DB_PARAMS['user']}'@'%';")
        return False

    except Exception as e:
        print(f"  ❌ Erro inesperado: {type(e).__name__}: {e}")
        return False


# ── Runner Principal ──────────────────────────────────────────────────────────

async def main(check_only: bool = False, create_only: bool = False) -> int:
    """
    Executa as verificações em sequência.
    Retorna 0 em caso de sucesso, 1 em caso de falha.
    """
    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║       Vigil.AI — Validação do Banco de Dados MySQL       ║")
    print("╚══════════════════════════════════════════════════════════╝")

    # ── Passo 1: Conexão ──────────────────────────────────────────
    if not create_only:
        connection_ok = await check_connection()
        if not connection_ok:
            print("\n❌ Validação interrompida: banco de dados inacessível.\n")
            return 1

        if check_only:
            print("\n✅ Verificação de conexão concluída (--check-only).\n")
            return 0

    # ── Passo 2: Tabela ───────────────────────────────────────────
    table_ok = await check_and_create_table()

    print()
    print("=" * 60)
    if table_ok:
        print("  ✅ Todas as verificações passaram! Sistema pronto.")
    else:
        print("  ❌ Uma ou mais verificações falharam. Veja os erros acima.")
    print("=" * 60)
    print()

    return 0 if table_ok else 1


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Valida conexão e estrutura da tabela MySQL do Vigil.AI"
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Apenas verifica a conexão, sem criar/verificar tabelas",
    )
    parser.add_argument(
        "--create-only",
        action="store_true",
        help="Pula o teste de conexão e vai direto para criação da tabela",
    )
    args = parser.parse_args()

    exit_code = asyncio.run(main(
        check_only=args.check_only,
        create_only=args.create_only,
    ))
    sys.exit(exit_code)
