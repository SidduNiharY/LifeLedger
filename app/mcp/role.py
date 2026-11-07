READONLY_ROLE = "lifeledger_ro"


def readonly_role_statements() -> list[str]:
    return [
        (
            "DO $$ BEGIN "
            "IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'lifeledger_ro') THEN "
            "CREATE ROLE lifeledger_ro NOLOGIN; "
            "END IF; "
            "END $$;"
        ),
        "GRANT USAGE ON SCHEMA public TO lifeledger_ro;",
        "GRANT SELECT ON ALL TABLES IN SCHEMA public TO lifeledger_ro;",
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO lifeledger_ro;",
    ]
