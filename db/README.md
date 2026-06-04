# Database

- **Local:** `docker compose up -d postgres` applies `schema.sql` on first start.
- **Production:** AlloyDB (PostgreSQL-compatible); same schema, connection via `DATABASE_URL` / Secret Manager.

Schema is a starting point—finance column mapping and migrations may change tables later.
