"""Initial schema — Tebeoteca Digital v1.3.

Revision ID: 0001
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, ENUM as PGEnum, JSONB, UUID

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    for enum_sql in [
        "CREATE TYPE comic_tradition AS ENUM ('american','franco_belgian','manga','tebeo','fumetti','manhwa','manhua','british','other')",
        "CREATE TYPE creator_role AS ENUM ('writer','penciler','inker','colorist','letterer','cover_artist','editor','translator')",
        "CREATE TYPE issue_format AS ENUM ('single_issue','trade_paperback','hardcover','omnibus','graphic_novel','album','manga_tankobon','digital')",
        "CREATE TYPE file_format AS ENUM ('cbz','cbr','cb7','pdf','epub')",
        "CREATE TYPE wishlist_status AS ENUM ('wanted','searching','downloading','downloaded','imported','failed')",
        "CREATE TYPE reading_status AS ENUM ('unread','reading','completed','on_hold','dropped')",
    ]:
        op.execute(enum_sql)

    op.create_table("publishers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("country", sa.String(100)),
        sa.Column("website", sa.String(500)),
        sa.Column("comic_vine_id", sa.BigInteger, unique=True),
        sa.Column("metadata", JSONB, server_default="{}"),
        sa.Column("metadata_source", sa.String(20)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_table("imprints",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("publisher_id", UUID(as_uuid=True), sa.ForeignKey("publishers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.UniqueConstraint("publisher_id", "name"),
    )
    op.create_table("universes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("publisher_id", UUID(as_uuid=True), sa.ForeignKey("publishers.id", ondelete="SET NULL")),
        sa.Column("description", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_table("genres",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("name_es", sa.String(100)),
        sa.Column("description", sa.Text),
    )
    op.create_table("creators",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("sort_name", sa.String(255)),
        sa.Column("nationality", sa.String(100)),
        sa.Column("birth_year", sa.SmallInteger),
        sa.Column("death_year", sa.SmallInteger),
        sa.Column("biography", sa.Text),
        sa.Column("comic_vine_id", sa.BigInteger, unique=True),
        sa.Column("photo_url", sa.String(500)),
        sa.Column("metadata", JSONB, server_default="{}"),
        sa.Column("metadata_source", sa.String(20)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_table("characters",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("real_name", sa.String(255)),
        sa.Column("universe_id", UUID(as_uuid=True), sa.ForeignKey("universes.id", ondelete="SET NULL")),
        sa.Column("publisher_id", UUID(as_uuid=True), sa.ForeignKey("publishers.id", ondelete="SET NULL")),
        sa.Column("first_appearance_year", sa.SmallInteger),
        sa.Column("description", sa.Text),
        sa.Column("comic_vine_id", sa.BigInteger, unique=True),
        sa.Column("image_url", sa.String(500)),
        sa.Column("metadata", JSONB, server_default="{}"),
        sa.Column("metadata_source", sa.String(20)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_table("series",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("sort_title", sa.String(500)),
        sa.Column("publisher_id", UUID(as_uuid=True), sa.ForeignKey("publishers.id", ondelete="SET NULL")),
        sa.Column("imprint_id", UUID(as_uuid=True), sa.ForeignKey("imprints.id", ondelete="SET NULL")),
        sa.Column("universe_id", UUID(as_uuid=True), sa.ForeignKey("universes.id", ondelete="SET NULL")),
        sa.Column("tradition", PGEnum("american","franco_belgian","manga","tebeo","fumetti","manhwa","manhua","british","other", name="comic_tradition", create_type=False), nullable=False, server_default="american"),
        sa.Column("start_year", sa.SmallInteger),
        sa.Column("end_year", sa.SmallInteger),
        sa.Column("total_issues", sa.Integer),
        sa.Column("status", sa.String(50), server_default="ongoing"),
        sa.Column("description", sa.Text),
        sa.Column("comic_vine_id", sa.BigInteger, unique=True),
        sa.Column("cover_url", sa.String(500)),
        sa.Column("metadata", JSONB, server_default="{}"),
        sa.Column("metadata_source", sa.String(20)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_table("story_arcs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("is_crossover", sa.Boolean, server_default="false"),
        sa.Column("universe_id", UUID(as_uuid=True), sa.ForeignKey("universes.id", ondelete="SET NULL")),
        sa.Column("comic_vine_id", sa.BigInteger, unique=True),
        sa.Column("metadata", JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_table("issues",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("series_id", UUID(as_uuid=True), sa.ForeignKey("series.id", ondelete="CASCADE"), nullable=False),
        sa.Column("issue_number", sa.String(20)),
        sa.Column("volume", sa.Integer, server_default="1"),
        sa.Column("title", sa.String(500)),
        sa.Column("release_date", sa.Date),
        sa.Column("format", PGEnum("single_issue","trade_paperback","hardcover","omnibus","graphic_novel","album","manga_tankobon","digital", name="issue_format", create_type=False), server_default="single_issue"),
        sa.Column("page_count", sa.Integer),
        sa.Column("isbn", sa.String(20)),
        sa.Column("synopsis", sa.Text),
        sa.Column("cover_url", sa.String(500)),
        sa.Column("comic_vine_id", sa.BigInteger, unique=True),
        sa.Column("sort_order", sa.Float),
        sa.Column("metadata", JSONB, server_default="{}"),
        sa.Column("metadata_source", sa.String(20)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.UniqueConstraint("series_id", "issue_number", "volume"),
    )
    op.create_table("series_genres",
        sa.Column("series_id", UUID(as_uuid=True), sa.ForeignKey("series.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("genre_id",  UUID(as_uuid=True), sa.ForeignKey("genres.id",  ondelete="CASCADE"), primary_key=True),
    )
    op.create_table("issue_creators",
        sa.Column("issue_id",   UUID(as_uuid=True), sa.ForeignKey("issues.id",   ondelete="CASCADE"), primary_key=True),
        sa.Column("creator_id", UUID(as_uuid=True), sa.ForeignKey("creators.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role", PGEnum("writer","penciler","inker","colorist","letterer","cover_artist","editor","translator", name="creator_role", create_type=False), primary_key=True),
    )
    op.create_table("issue_characters",
        sa.Column("issue_id",     UUID(as_uuid=True), sa.ForeignKey("issues.id",     ondelete="CASCADE"), primary_key=True),
        sa.Column("character_id", UUID(as_uuid=True), sa.ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("is_main", sa.Boolean, server_default="false"),
    )
    op.create_table("story_arc_issues",
        sa.Column("story_arc_id",  UUID(as_uuid=True), sa.ForeignKey("story_arcs.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("issue_id",      UUID(as_uuid=True), sa.ForeignKey("issues.id",      ondelete="CASCADE"), primary_key=True),
        sa.Column("reading_order", sa.Integer, nullable=False),
    )
    op.create_table("tags",
        sa.Column("id",    UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name",  sa.String(100), nullable=False, unique=True),
        sa.Column("color", sa.String(7)),
    )
    op.create_table("issue_tags",
        sa.Column("issue_id", UUID(as_uuid=True), sa.ForeignKey("issues.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tag_id",   UUID(as_uuid=True), sa.ForeignKey("tags.id",   ondelete="CASCADE"), primary_key=True),
    )
    op.create_table("files",
        sa.Column("id",               UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("issue_id",         UUID(as_uuid=True), sa.ForeignKey("issues.id", ondelete="SET NULL")),
        sa.Column("file_path",        sa.String(1000), nullable=False, unique=True),
        sa.Column("file_name",        sa.String(500), nullable=False),
        sa.Column("file_format",      PGEnum("cbz","cbr","cb7","pdf","epub", name="file_format", create_type=False), nullable=False),
        sa.Column("file_size_bytes",  sa.BigInteger),
        sa.Column("sha256_hash",      sa.String(64)),
        sa.Column("source_tag",       sa.String(50)),
        sa.Column("width_px",         sa.Integer),
        sa.Column("covered_issue_ids", ARRAY(UUID(as_uuid=True)), server_default="{}"),
        sa.Column("quality",          sa.String(50)),
        sa.Column("is_verified",      sa.Boolean, server_default="false"),
        sa.Column("metadata_source",  sa.String(20)),
        sa.Column("imported_at",      sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("metadata",         JSONB, server_default="{}"),
    )
    op.create_table("wishlist",
        sa.Column("id",               UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("series_id",        UUID(as_uuid=True), sa.ForeignKey("series.id", ondelete="CASCADE")),
        sa.Column("issue_id",         UUID(as_uuid=True), sa.ForeignKey("issues.id", ondelete="CASCADE")),
        sa.Column("status",           PGEnum("wanted","searching","downloading","downloaded","imported","failed", name="wishlist_status", create_type=False), server_default="wanted"),
        sa.Column("priority",         sa.Integer, server_default="5"),
        sa.Column("search_query",     sa.String(500)),
        sa.Column("locked_fields",    ARRAY(sa.String), server_default="{}"),
        sa.Column("added_at",         sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("last_searched_at", sa.DateTime(timezone=True)),
        sa.Column("downloaded_at",    sa.DateTime(timezone=True)),
        sa.Column("notes",            sa.Text),
        sa.CheckConstraint("series_id IS NOT NULL OR issue_id IS NOT NULL", name="wishlist_target_check"),
    )
    op.create_table("reading_progress",
        sa.Column("id",           UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("issue_id",     UUID(as_uuid=True), sa.ForeignKey("issues.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("status",       PGEnum("unread","reading","completed","on_hold","dropped", name="reading_status", create_type=False), server_default="unread"),
        sa.Column("current_page", sa.Integer, server_default="0"),
        sa.Column("rating",       sa.SmallInteger),
        sa.Column("started_at",   sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("notes",        sa.Text),
    )
    op.create_table("reading_lists",
        sa.Column("id",          UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name",        sa.String(255), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("created_at",  sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_table("reading_list_items",
        sa.Column("reading_list_id", UUID(as_uuid=True), sa.ForeignKey("reading_lists.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("issue_id",        UUID(as_uuid=True), sa.ForeignKey("issues.id",         ondelete="CASCADE"), primary_key=True),
        sa.Column("position",        sa.Integer, nullable=False),
    )

    # Índices
    for idx in [
        "CREATE INDEX idx_issues_series ON issues(series_id)",
        "CREATE INDEX idx_issues_sort ON issues(series_id, sort_order)",
        "CREATE INDEX idx_files_hash ON files(sha256_hash)",
        "CREATE INDEX idx_files_issue ON files(issue_id)",
        "CREATE INDEX idx_wishlist_status ON wishlist(status)",
        "CREATE INDEX idx_wishlist_priority ON wishlist(status, priority)",
        "CREATE INDEX idx_series_tradition ON series(tradition)",
        "CREATE INDEX idx_issue_creators_creator ON issue_creators(creator_id)",
        # Full-text
        "CREATE INDEX idx_series_title_fts ON series USING GIN (to_tsvector('spanish', title))",
        "CREATE INDEX idx_issues_synopsis_fts ON issues USING GIN (to_tsvector('spanish', COALESCE(synopsis,'')))",
        "CREATE INDEX idx_creators_name_fts ON creators USING GIN (to_tsvector('simple', name))",
        # Trigram (fuzzy matching)
        "CREATE INDEX idx_series_title_trgm ON series USING GIN (title gin_trgm_ops)",
        "CREATE INDEX idx_creators_name_trgm ON creators USING GIN (name gin_trgm_ops)",
        # JSONB
        "CREATE INDEX idx_series_metadata ON series USING GIN (metadata)",
        "CREATE INDEX idx_issues_metadata ON issues USING GIN (metadata)",
        "CREATE INDEX idx_files_metadata ON files USING GIN (metadata)",
    ]:
        op.execute(idx)

    # Trigger updated_at
    op.execute("""
        CREATE OR REPLACE FUNCTION fn_update_timestamp()
        RETURNS TRIGGER AS $$
        BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
        $$ LANGUAGE plpgsql
    """)
    for t in ("publishers","creators","characters","series","issues"):
        op.execute(f"CREATE TRIGGER trg_{t}_updated BEFORE UPDATE ON {t} FOR EACH ROW EXECUTE FUNCTION fn_update_timestamp()")

    # Datos semilla
    op.execute("""
        INSERT INTO genres (id, name, name_es) VALUES
        (gen_random_uuid(),'superhero','Superh\u00e9roes'),
        (gen_random_uuid(),'sci_fi','Ciencia ficci\u00f3n'),
        (gen_random_uuid(),'fantasy','Fantas\u00eda'),
        (gen_random_uuid(),'horror','Terror'),
        (gen_random_uuid(),'crime_noir','Crimen / Noir'),
        (gen_random_uuid(),'humor','Humor'),
        (gen_random_uuid(),'adventure','Aventura'),
        (gen_random_uuid(),'historical','Hist\u00f3rico'),
        (gen_random_uuid(),'slice_of_life','Costumbrista'),
        (gen_random_uuid(),'underground','Underground / Alternativo'),
        (gen_random_uuid(),'autobiographical','Autobiogr\u00e1fico'),
        (gen_random_uuid(),'sports','Deportivo'),
        (gen_random_uuid(),'mecha','Mecha')
    """)
    op.execute("""
        INSERT INTO publishers (id, name, country) VALUES
        (gen_random_uuid(),'Marvel Comics','USA'),
        (gen_random_uuid(),'DC Comics','USA'),
        (gen_random_uuid(),'Image Comics','USA'),
        (gen_random_uuid(),'Dark Horse Comics','USA'),
        (gen_random_uuid(),'Norma Editorial','Espa\u00f1a'),
        (gen_random_uuid(),'Planeta C\u00f3mic','Espa\u00f1a'),
        (gen_random_uuid(),'Panini Comics','Italia'),
        (gen_random_uuid(),'ECC Ediciones','Espa\u00f1a'),
        (gen_random_uuid(),'Ivr\u00e9a','Espa\u00f1a'),
        (gen_random_uuid(),'Dargaud','Francia'),
        (gen_random_uuid(),'Dupuis','B\u00e9lgica'),
        (gen_random_uuid(),'Casterman','Francia'),
        (gen_random_uuid(),'Sh\u016beisha','Jap\u00f3n'),
        (gen_random_uuid(),'K\u014ddansha','Jap\u00f3n'),
        (gen_random_uuid(),'Sergio Bonelli Editore','Italia'),
        (gen_random_uuid(),'2000 AD','Reino Unido')
    """)


def downgrade() -> None:
    for t in ("reading_list_items","reading_lists","reading_progress","wishlist",
              "files","issue_tags","tags","story_arc_issues","issue_characters",
              "issue_creators","series_genres","issues","story_arcs","series",
              "characters","creators","genres","universes","imprints","publishers"):
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
    for e in ("comic_tradition","creator_role","issue_format","file_format","wishlist_status","reading_status"):
        op.execute(f"DROP TYPE IF EXISTS {e} CASCADE")
    op.execute("DROP FUNCTION IF EXISTS fn_update_timestamp() CASCADE")
    op.execute('DROP EXTENSION IF EXISTS "uuid-ossp" CASCADE')
    op.execute("DROP EXTENSION IF EXISTS pg_trgm CASCADE")
