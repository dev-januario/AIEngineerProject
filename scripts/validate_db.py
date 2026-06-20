#!/usr/bin/env python3
"""
validate_db.py — Script de Validação do Banco de Dados MySQL
=============================================================
Executa verificações críticas antes de subir a aplicação:

  1. Testa a conexão com o MySQL
  2. Verifica se TODAS as tabelas existem. Se não existirem, cria automaticamente.

Tabelas gerenciadas:
  - leads             → ciclo de vida completo dos participantes
  - events            → dados do evento Vigil Summit
  - message_templates → templates editáveis com suporte a variáveis
  - admin_users       → usuários do painel administrativo

Uso:
  python scripts/validate_db.py
  python scripts/validate_db.py --check-only

Variáveis de ambiente (lidas do .env na raiz do projeto):
  DATABASE_URL=mysql+aiomysql://vigil:vigil123@localhost:3306/vigildb
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "vigil_agent"))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT_DIR / ".env")
except ImportError:
    pass

import aiomysql


# ── Configuração ──────────────────────────────────────────────────────────────

def _parse_mysql_url(url: str) -> dict:
    url = url.replace("mysql+aiomysql://", "").replace("mysql://", "")
    credentials, rest = url.split("@", 1)
    user, password = credentials.split(":", 1)
    host_port, database = rest.split("/", 1)
    if ":" in host_port:
        host, port = host_port.split(":", 1)
        port = int(port)
    else:
        host = host_port
        port = 3306
    return {"host": host, "port": port, "user": user, "password": password, "db": database}


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "mysql+aiomysql://vigil:vigil123@localhost:3306/vigildb",
)
DB_PARAMS = _parse_mysql_url(DATABASE_URL)


# ── DDL de todas as tabelas ───────────────────────────────────────────────────

TABLES: list[tuple[str, str]] = []

TABLES.append(("leads", """
CREATE TABLE IF NOT EXISTS leads (
    id              INT             NOT NULL AUTO_INCREMENT,
    name            VARCHAR(255)    NOT NULL,
    email           VARCHAR(255)    NOT NULL UNIQUE,
    phone           VARCHAR(50)     NULL,
    company         VARCHAR(255)    NULL,
    role            VARCHAR(255)    NULL,
    company_size    VARCHAR(50)     NULL,
    sector          VARCHAR(100)    NULL,
    linkedin_url    VARCHAR(500)    NULL,
    enrichment_data     JSON        NULL COMMENT 'Dados enriquecidos pelo agente de IA',
    qualification_score FLOAT       NULL COMMENT 'Score ICP de 0.0 a 1.0',
    status          ENUM(
                        'new', 'enriched', 'contacted', 'confirmed',
                        'declined', 'no_response', 'attended', 'no_show',
                        'followed_up', 'meeting_booked', 'out_of_icp'
                    ) NOT NULL DEFAULT 'new',
    funnel_phase    ENUM(
                        'capture', 'enrichment', 'pre_event', 'post_event', 'closed'
                    ) NOT NULL DEFAULT 'capture',
    communication_log   JSON        NULL COMMENT 'Log de mensagens enviadas e recebidas',
    last_contacted_at   DATETIME    NULL,
    contact_attempts    INT         NOT NULL DEFAULT 0,
    event_notes     TEXT            NULL,
    attended        TINYINT(1)      NULL,
    with_companion  TINYINT(1)      NOT NULL DEFAULT 0,
    companion_email         VARCHAR(255)    NULL     COMMENT 'Email do acompanhante; recebe convite para preencher o formulario',
    companion_relationship  VARCHAR(50)     NULL     COMMENT 'Vinculo: colleague | friend | spouse | child | other',
    is_companion            TINYINT(1)      NOT NULL DEFAULT 0 COMMENT 'True quando este lead e um acompanhante criado a partir de outro lead',
    companion_of_lead_id    INT             NULL     COMMENT 'ID do lead principal que gerou este acompanhante',
    lgpd_consent    TINYINT(1)      NOT NULL DEFAULT 0,
    consent_at      DATETIME        NULL,
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_email         (email),
    INDEX idx_status        (status),
    INDEX idx_funnel_phase  (funnel_phase),
    INDEX idx_created_at    (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Leads do evento Vigil Summit — ciclo de vida completo do funil';
"""))

TABLES.append(("events", """
CREATE TABLE IF NOT EXISTS events (
    id                          INT             NOT NULL AUTO_INCREMENT,
    name                        VARCHAR(255)    NOT NULL DEFAULT 'Vigil Summit',
    event_date                  VARCHAR(50)     NULL     COMMENT 'Data ex.: 2026-07-15',
    event_time                  VARCHAR(20)     NULL     COMMENT 'Horario ex.: 09:00',
    location                    VARCHAR(500)    NULL,
    description                 TEXT            NULL,
    speakers                    JSON            NULL     COMMENT 'Lista de palestrantes',
    post_event_delay_minutes    INT             NOT NULL DEFAULT 3,
    pre_event_reminder_days     JSON            NULL     COMMENT 'Dias antes do evento para disparar lembretes ex.: [30,15,7,3,1]',
    pre_event_send_time         VARCHAR(5)      NOT NULL DEFAULT '09:00' COMMENT 'Horario de disparo diario HH:MM',
    status                      ENUM('DRAFT', 'ACTIVE', 'ENDED') NOT NULL DEFAULT 'ACTIVE',
    scheduled_end_at            DATETIME        NULL,
    ended_at                    DATETIME        NULL,
    created_at                  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at                  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Dados do evento Vigil Summit';
"""))

TABLES.append(("message_templates", """
CREATE TABLE IF NOT EXISTS message_templates (
    id                  INT             NOT NULL AUTO_INCREMENT,
    name                VARCHAR(255)    NOT NULL,
    phase               ENUM(
                            'pre_event',
                            'pre_event_participant',
                            'pre_event_with_companion',
                            'pre_event_companion_pending',
                            'confirmation',
                            'post_event',
                            'post_event_attended',
                            'post_event_no_show',
                            'reply'
                        ) NOT NULL,
    channel             ENUM('EMAIL', 'WHATSAPP', 'BOTH') NOT NULL,
    subject             VARCHAR(500)    NULL,
    body                TEXT            NOT NULL,
    sequence_order      INT             NOT NULL DEFAULT 1,
    days_before_event   INT             NULL     COMMENT 'Dias antes do evento para disparar (NULL = sem restricao de data)',
    is_active           TINYINT(1)      NOT NULL DEFAULT 1,
    created_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_phase             (phase),
    INDEX idx_days_before_event (days_before_event),
    INDEX idx_active            (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Templates de mensagem editaveis pelo painel administrativo';
"""))

TABLES.append(("admin_users", """
CREATE TABLE IF NOT EXISTS admin_users (
    id              INT             NOT NULL AUTO_INCREMENT,
    username        VARCHAR(100)    NOT NULL UNIQUE,
    hashed_password VARCHAR(255)    NOT NULL,
    full_name       VARCHAR(255)    NULL,
    is_active       TINYINT(1)      NOT NULL DEFAULT 1,
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Usuarios com acesso ao painel administrativo do Vigil Summit';
"""))


# ── Colunas novas que podem não existir em bancos já criados ─────────────────
# Lista de (tabela, coluna, DDL da coluna)
ALTER_COLUMNS: list[tuple[str, str, str]] = [
    (
        "leads",
        "companion_email",
        "ALTER TABLE `leads` ADD COLUMN `companion_email` VARCHAR(255) NULL "
        "COMMENT 'Email do acompanhante; recebe convite para preencher o formulario' "
        "AFTER `with_companion`",
    ),
    (
        "leads",
        "companion_relationship",
        "ALTER TABLE `leads` ADD COLUMN `companion_relationship` VARCHAR(50) NULL "
        "COMMENT 'Vinculo: colleague | friend | spouse | child | other' "
        "AFTER `companion_email`",
    ),
    (
        "leads",
        "attended",
        "ALTER TABLE `leads` ADD COLUMN `attended` TINYINT(1) NULL "
        "COMMENT 'Presenca confirmada via QR Code no evento' "
        "AFTER `event_notes`",
    ),
    # ── Colunas novas da régua pré-evento (adicionadas na conversa 8003e425) ──
    (
        "events",
        "pre_event_reminder_days",
        "ALTER TABLE `events` ADD COLUMN `pre_event_reminder_days` JSON NULL "
        "COMMENT 'Dias antes do evento para disparar lembretes ex.: [30,15,7,3,1]' "
        "AFTER `post_event_delay_minutes`",
    ),
    (
        "events",
        "pre_event_send_time",
        "ALTER TABLE `events` ADD COLUMN `pre_event_send_time` VARCHAR(5) NOT NULL DEFAULT '09:00' "
        "COMMENT 'Horario de disparo diario HH:MM' "
        "AFTER `pre_event_reminder_days`",
    ),
    # ── Colunas novas em message_templates ────────────────────────────────────
    (
        "message_templates",
        "days_before_event",
        "ALTER TABLE `message_templates` ADD COLUMN `days_before_event` INT NULL "
        "COMMENT 'Dias antes do evento para disparar (NULL = sem restricao de data)' "
        "AFTER `sequence_order`",
    ),
    # ── Colunas de acompanhante ───────────────────────────────────────────────
    (
        "leads",
        "is_companion",
        "ALTER TABLE `leads` ADD COLUMN `is_companion` TINYINT(1) NOT NULL DEFAULT 0 "
        "COMMENT 'True quando este lead e um acompanhante criado a partir de outro lead' "
        "AFTER `companion_relationship`",
    ),
    (
        "leads",
        "companion_of_lead_id",
        "ALTER TABLE `leads` ADD COLUMN `companion_of_lead_id` INT NULL "
        "COMMENT 'ID do lead principal que gerou este acompanhante' "
        "AFTER `is_companion`",
    ),
]


# ── Migração de ENUMs ──────────────────────────────────────────────────────
# Lista de (tabela, coluna, valor_esperado, ALTER_DDL_completo)
ALTER_ENUMS: list[tuple[str, str, str, str]] = [
    (
        "message_templates",
        "phase",
        "pre_event_participant",          # valor sentinela: se não existe, o ENUM está desatualizado
        "ALTER TABLE `message_templates` MODIFY COLUMN `phase` "
        "ENUM('pre_event','pre_event_participant','pre_event_with_companion',"
        "'pre_event_companion_pending','confirmation','post_event',"
        "'post_event_attended','post_event_no_show','reply') NOT NULL",
    ),
    (
        "message_templates",
        "channel",
        "EMAIL",
        "ALTER TABLE `message_templates` MODIFY COLUMN `channel` "
        "ENUM('EMAIL', 'WHATSAPP', 'BOTH') NOT NULL",
    ),
    (
        "events",
        "status",
        "ACTIVE",
        "ALTER TABLE `events` MODIFY COLUMN `status` "
        "ENUM('DRAFT', 'ACTIVE', 'ENDED') NOT NULL DEFAULT 'ACTIVE'",
    ),
    # ── Novos status e phases adicionados na implementação de qualificação ──
    (
        "leads",
        "status",
        "pending_review",
        "ALTER TABLE `leads` MODIFY COLUMN `status` "
        "ENUM('new','enriched','contacted','confirmed','declined',"
        "'no_response','attended','no_show','followed_up',"
        "'meeting_booked','out_of_icp','pending_review') NOT NULL DEFAULT 'new'",
    ),
    (
        "leads",
        "funnel_phase",
        "companion_pending",
        "ALTER TABLE `leads` MODIFY COLUMN `funnel_phase` "
        "ENUM('capture','enrichment','pre_event','companion_pending','post_event','closed') NOT NULL DEFAULT 'capture'",
    ),
]


# ── 1. Teste de Conexão ───────────────────────────────────────────────────────

async def check_connection() -> bool:
    print("\n" + "=" * 60)
    print("  VERIFICACAO 1 — Conexao com o MySQL")
    print("=" * 60)
    print(f"  Host     : {DB_PARAMS['host']}:{DB_PARAMS['port']}")
    print(f"  Database : {DB_PARAMS['db']}")
    print(f"  Usuario  : {DB_PARAMS['user']}")
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
        print(f"  OK  Conexao estabelecida com sucesso!")
        print(f"  MySQL: {version}")
        return True

    except aiomysql.OperationalError as e:
        errno, msg = e.args
        print(f"  ERRO Falha na conexao! [{errno}]: {msg}")
        if errno == 1045:
            print("  Dica: Verifique usuario/senha no .env")
        elif errno == 2003:
            print("  Dica: MySQL nao esta rodando. Execute: docker compose up -d")
        elif errno == 1049:
            print(f"  Dica: Banco '{DB_PARAMS['db']}' nao existe. Crie-o primeiro.")
        return False
    except Exception as e:
        print(f"  ERRO inesperado: {type(e).__name__}: {e}")
        return False


# ── 2. Verificacao e Criacao das Tabelas ─────────────────────────────────────

async def check_and_create_tables() -> bool:
    print("\n" + "=" * 60)
    print("  VERIFICACAO 2 — Estrutura das Tabelas")
    print("=" * 60)

    all_ok = True

    try:
        conn = await aiomysql.connect(
            host=DB_PARAMS["host"],
            port=DB_PARAMS["port"],
            user=DB_PARAMS["user"],
            password=DB_PARAMS["password"],
            db=DB_PARAMS["db"],
            connect_timeout=5,
        )

        for table_name, ddl in TABLES:
            print(f"\n  Tabela `{table_name}`:")
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_schema = %s AND table_name = %s",
                    (DB_PARAMS["db"], table_name),
                )
                exists = (await cur.fetchone())[0] > 0

                if exists:
                    await cur.execute(f"SELECT COUNT(*) FROM `{table_name}`")
                    total = (await cur.fetchone())[0]
                    print(f"     OK — Existe com {total} registro(s)")
                else:
                    print(f"     AVISO — Nao encontrada. Criando...")
                    await cur.execute(ddl)
                    await conn.commit()
                    await cur.execute(
                        "SELECT COUNT(*) FROM information_schema.tables "
                        "WHERE table_schema = %s AND table_name = %s",
                        (DB_PARAMS["db"], table_name),
                    )
                    created = (await cur.fetchone())[0] > 0
                    if created:
                        print(f"     OK — Criada com sucesso!")
                    else:
                        print(f"     ERRO — Falha ao criar. Verifique as permissoes do usuario MySQL.")
                        all_ok = False

        conn.close()

    except Exception as e:
        print(f"\n  ERRO: {type(e).__name__}: {e}")
        return False

    return all_ok


# ── 3. Migração de Colunas Novas ──────────────────────────────────────────────

async def migrate_columns() -> bool:
    """Adiciona colunas que possam ter sido incluidas apos a criacao inicial do banco."""
    print("\n" + "=" * 60)
    print("  VERIFICACAO 3 — Migração de Colunas Novas")
    print("=" * 60)

    all_ok = True
    try:
        conn = await aiomysql.connect(
            host=DB_PARAMS["host"],
            port=DB_PARAMS["port"],
            user=DB_PARAMS["user"],
            password=DB_PARAMS["password"],
            db=DB_PARAMS["db"],
            connect_timeout=5,
        )

        for table_name, col_name, ddl in ALTER_COLUMNS:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT COUNT(*) FROM information_schema.columns "
                    "WHERE table_schema = %s AND table_name = %s AND column_name = %s",
                    (DB_PARAMS["db"], table_name, col_name),
                )
                exists = (await cur.fetchone())[0] > 0

                if exists:
                    print(f"  OK  `{table_name}`.`{col_name}` já existe")
                else:
                    print(f"  AVISO  `{table_name}`.`{col_name}` não existe. Adicionando...")
                    await cur.execute(ddl)
                    await conn.commit()
                    print(f"  OK  `{table_name}`.`{col_name}` adicionada com sucesso!")

        conn.close()

    except Exception as e:
        print(f"\n  ERRO: {type(e).__name__}: {e}")
        return False

    return all_ok


# ── 4. Migração de ENUMs ──────────────────────────────────────────────────────

async def migrate_enums() -> bool:
    """Expande ENUMs que precisem de novos valores em bancos já existentes."""
    print("\n" + "=" * 60)
    print("  VERIFICACAO 4 — Migração de ENUMs")
    print("=" * 60)

    all_ok = True
    try:
        conn = await aiomysql.connect(
            host=DB_PARAMS["host"],
            port=DB_PARAMS["port"],
            user=DB_PARAMS["user"],
            password=DB_PARAMS["password"],
            db=DB_PARAMS["db"],
            connect_timeout=5,
        )

        for table_name, col_name, expected_value, ddl in ALTER_ENUMS:
            async with conn.cursor() as cur:
                # Verifica se o valor já existe na definição do ENUM
                await cur.execute(
                    "SELECT COLUMN_TYPE FROM information_schema.columns "
                    "WHERE table_schema = %s AND table_name = %s AND column_name = %s",
                    (DB_PARAMS["db"], table_name, col_name),
                )
                row = await cur.fetchone()
                if not row:
                    print(f"  AVISO  `{table_name}`.`{col_name}` não encontrada — pulando")
                    continue

                col_type = row[0]
                if expected_value in col_type:
                    print(f"  OK  `{table_name}`.`{col_name}` já contém '{expected_value}'")
                else:
                    print(f"  AVISO  `{table_name}`.`{col_name}` desatualizado. Expandindo ENUM...")
                    await cur.execute(ddl)
                    await conn.commit()
                    print(f"  OK  ENUM expandido com sucesso!")

        conn.close()

    except Exception as e:
        print(f"\n  ERRO: {type(e).__name__}: {e}")
        return False

    return all_ok

async def main(check_only: bool = False) -> int:
    print()
    print("=" * 60)
    print("   Vigil.AI — Validacao do Banco de Dados MySQL")
    print("=" * 60)

    connection_ok = await check_connection()
    if not connection_ok:
        print("\nERRO: Banco de dados inacessivel.\n")
        return 1

    if check_only:
        print("\nOK: Verificacao de conexao concluida (--check-only).\n")
        return 0

    tables_ok  = await check_and_create_tables()
    columns_ok = await migrate_columns()
    enums_ok   = await migrate_enums()

    print()
    print("=" * 60)
    if tables_ok and columns_ok and enums_ok:
        print("  OK: Todas as verificacoes passaram! Sistema pronto.")
    else:
        print("  ERRO: Uma ou mais verificacoes falharam.")
    print("=" * 60)
    print()

    return 0 if (tables_ok and columns_ok and enums_ok) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Valida conexao e estrutura do banco MySQL do Vigil.AI"
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Apenas verifica a conexao, sem criar/verificar tabelas",
    )
    args = parser.parse_args()
    exit_code = asyncio.run(main(check_only=args.check_only))
    sys.exit(exit_code)
