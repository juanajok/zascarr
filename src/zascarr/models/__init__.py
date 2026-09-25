"""Modelos ORM de ZascArr — mapeo 1:1 con tebeoteca_schema.sql."""
import enum
from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Computed,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from zascarr.database import Base

# ── Enums ──────────────────────────────────────────────────────────────────────

class ComicTradition(str, enum.Enum):
    AMERICAN      = "american"
    FRANCO_BELGIAN = "franco_belgian"
    MANGA         = "manga"
    TEBEO         = "tebeo"
    FUMETTI       = "fumetti"
    MANHWA        = "manhwa"
    MANHUA        = "manhua"
    BRITISH       = "british"
    OTHER         = "other"

class CreatorRole(str, enum.Enum):
    WRITER      = "writer"
    PENCILER    = "penciler"
    INKER       = "inker"
    COLORIST    = "colorist"
    LETTERER    = "letterer"
    COVER_ARTIST = "cover_artist"
    EDITOR      = "editor"
    TRANSLATOR  = "translator"

class IssueFormat(str, enum.Enum):
    SINGLE_ISSUE    = "single_issue"
    TRADE_PAPERBACK = "trade_paperback"
    HARDCOVER       = "hardcover"
    OMNIBUS         = "omnibus"
    GRAPHIC_NOVEL   = "graphic_novel"
    ALBUM           = "album"
    MANGA_TANKOBON  = "manga_tankobon"
    DIGITAL         = "digital"

class FileFormat(str, enum.Enum):
    CBZ  = "cbz"
    CBR  = "cbr"
    CB7  = "cb7"
    PDF  = "pdf"
    EPUB = "epub"

class WishlistStatus(str, enum.Enum):
    WANTED      = "wanted"
    SEARCHING   = "searching"
    DOWNLOADING = "downloading"
    DOWNLOADED  = "downloaded"
    IMPORTED    = "imported"
    FAILED      = "failed"

class ReadingStatus(str, enum.Enum):
    UNREAD    = "unread"
    READING   = "reading"
    COMPLETED = "completed"
    ON_HOLD   = "on_hold"
    DROPPED   = "dropped"

class MetadataSource(str, enum.Enum):
    COMIC_VINE    = "comic_vine"
    GCD           = "gcd"
    ANILIST       = "anilist"
    TEBEOSFERA    = "tebeosfera"
    COMICINFO_XML = "comicinfo_xml"
    MANUAL        = "manual"


# ── Tablas M:N ─────────────────────────────────────────────────────────────────

series_genres = Table(
    "series_genres", Base.metadata,
    Column("series_id",  UUID(as_uuid=True), ForeignKey("series.id",   ondelete="CASCADE"), primary_key=True),
    Column("genre_id",   UUID(as_uuid=True), ForeignKey("genres.id",   ondelete="CASCADE"), primary_key=True),
)

issue_characters = Table(
    "issue_characters", Base.metadata,
    Column("issue_id",     UUID(as_uuid=True), ForeignKey("issues.id",     ondelete="CASCADE"), primary_key=True),
    Column("character_id", UUID(as_uuid=True), ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True),
    Column("is_main", Boolean, default=False),
)

issue_tags = Table(
    "issue_tags", Base.metadata,
    Column("issue_id", UUID(as_uuid=True), ForeignKey("issues.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id",   UUID(as_uuid=True), ForeignKey("tags.id",   ondelete="CASCADE"), primary_key=True),
)


# ── Modelos ────────────────────────────────────────────────────────────────────

class Publisher(Base):
    __tablename__ = "publishers"
    id:            Mapped[str]      = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name:          Mapped[str]      = mapped_column(String(255), unique=True, nullable=False)
    country:       Mapped[str|None] = mapped_column(String(100))
    website:       Mapped[str|None] = mapped_column(String(500))
    comic_vine_id: Mapped[int|None] = mapped_column(BigInteger, unique=True)
    metadata_:     Mapped[dict]     = mapped_column("metadata", JSONB, default=dict)
    metadata_source: Mapped[str|None] = mapped_column(String(20))
    created_at:    Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at:    Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    imprints:  Mapped[list["Imprint"]]  = relationship(back_populates="publisher", cascade="all, delete-orphan")
    series:    Mapped[list["Series"]]   = relationship(back_populates="publisher")
    universes: Mapped[list["Universe"]] = relationship(back_populates="publisher")


class Imprint(Base):
    __tablename__ = "imprints"
    __table_args__ = (UniqueConstraint("publisher_id", "name"),)
    id:           Mapped[str]      = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    publisher_id: Mapped[str]      = mapped_column(UUID(as_uuid=True), ForeignKey("publishers.id", ondelete="CASCADE"), nullable=False)
    name:         Mapped[str]      = mapped_column(String(255), nullable=False)
    created_at:   Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    publisher: Mapped["Publisher"] = relationship(back_populates="imprints")


class Universe(Base):
    __tablename__ = "universes"
    id:           Mapped[str]      = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name:         Mapped[str]      = mapped_column(String(255), unique=True, nullable=False)
    publisher_id: Mapped[str|None] = mapped_column(UUID(as_uuid=True), ForeignKey("publishers.id", ondelete="SET NULL"))
    description:  Mapped[str|None] = mapped_column(Text)
    created_at:   Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    publisher:   Mapped["Publisher|None"]  = relationship(back_populates="universes")
    characters:  Mapped[list["Character"]] = relationship(back_populates="universe")
    story_arcs:  Mapped[list["StoryArc"]]  = relationship(back_populates="universe")


class Genre(Base):
    __tablename__ = "genres"
    id:          Mapped[str]      = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name:        Mapped[str]      = mapped_column(String(100), unique=True, nullable=False)
    name_es:     Mapped[str|None] = mapped_column(String(100))
    description: Mapped[str|None] = mapped_column(Text)


class Creator(Base):
    __tablename__ = "creators"
    id:              Mapped[str]      = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name:            Mapped[str]      = mapped_column(String(255), nullable=False)
    sort_name:       Mapped[str|None] = mapped_column(String(255))
    nationality:     Mapped[str|None] = mapped_column(String(100))
    birth_year:      Mapped[int|None] = mapped_column(SmallInteger)
    death_year:      Mapped[int|None] = mapped_column(SmallInteger)
    biography:       Mapped[str|None] = mapped_column(Text)
    comic_vine_id:   Mapped[int|None] = mapped_column(BigInteger, unique=True)
    photo_url:       Mapped[str|None] = mapped_column(String(500))
    metadata_:       Mapped[dict]     = mapped_column("metadata", JSONB, default=dict)
    metadata_source: Mapped[str|None] = mapped_column(String(20))
    # H3 (peer review v2): campos que el enricher nunca sobrescribe aunque
    # metadata_source no sea 'manual' — bloqueo granular, no todo-o-nada.
    locked_fields:   Mapped[list]     = mapped_column(ARRAY(String), default=list)
    created_at:      Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at:      Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    issue_credits: Mapped[list["IssueCreator"]] = relationship(back_populates="creator")


class Character(Base):
    __tablename__ = "characters"
    id:                     Mapped[str]      = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name:                   Mapped[str]      = mapped_column(String(255), nullable=False)
    real_name:              Mapped[str|None] = mapped_column(String(255))
    universe_id:            Mapped[str|None] = mapped_column(UUID(as_uuid=True), ForeignKey("universes.id", ondelete="SET NULL"))
    publisher_id:           Mapped[str|None] = mapped_column(UUID(as_uuid=True), ForeignKey("publishers.id", ondelete="SET NULL"))
    first_appearance_year:  Mapped[int|None] = mapped_column(SmallInteger)
    description:            Mapped[str|None] = mapped_column(Text)
    comic_vine_id:          Mapped[int|None] = mapped_column(BigInteger, unique=True)
    image_url:              Mapped[str|None] = mapped_column(String(500))
    metadata_:              Mapped[dict]     = mapped_column("metadata", JSONB, default=dict)
    metadata_source:        Mapped[str|None] = mapped_column(String(20))
    locked_fields:          Mapped[list]     = mapped_column(ARRAY(String), default=list)
    created_at:             Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at:             Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    universe: Mapped["Universe|None"] = relationship(back_populates="characters")


class Series(Base):
    __tablename__ = "series"
    id:              Mapped[str]      = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    title:           Mapped[str]      = mapped_column(String(500), nullable=False)
    sort_title:      Mapped[str|None] = mapped_column(String(500))
    # H1 (peer review v2): columna generada por Postgres (f_title_norm(title),
    # ver migración 0006) — espejo de core.matcher.normalize_title. Nunca se
    # asigna desde Python; SQLAlchemy solo la lee de vuelta tras un refresh.
    title_norm:      Mapped[str|None] = mapped_column(Text, Computed("f_title_norm(title)", persisted=True))
    publisher_id:    Mapped[str|None] = mapped_column(UUID(as_uuid=True), ForeignKey("publishers.id", ondelete="SET NULL"))
    imprint_id:      Mapped[str|None] = mapped_column(UUID(as_uuid=True), ForeignKey("imprints.id", ondelete="SET NULL"))
    universe_id:     Mapped[str|None] = mapped_column(UUID(as_uuid=True), ForeignKey("universes.id", ondelete="SET NULL"))
    tradition:       Mapped[ComicTradition] = mapped_column(Enum(ComicTradition, name="comic_tradition", values_callable=lambda obj: [e.value for e in obj]), default=ComicTradition.AMERICAN)
    start_year:      Mapped[int|None] = mapped_column(SmallInteger)
    end_year:        Mapped[int|None] = mapped_column(SmallInteger)
    total_issues:    Mapped[int|None] = mapped_column(Integer)
    status:          Mapped[str]      = mapped_column(String(50), default="ongoing")
    description:     Mapped[str|None] = mapped_column(Text)
    comic_vine_id:   Mapped[int|None] = mapped_column(BigInteger, unique=True)
    # Fuente separada de comic_vine_id: AniList tiene su propio espacio de
    # IDs (manga/manhwa/manhua, que Comic Vine no indexa bien). Una serie
    # solo se enriquece con UNA de las fuentes según su tradition (ver
    # enricher.py), así que en la práctica nunca tienen más de una a la vez.
    anilist_id:      Mapped[int|None] = mapped_column(BigInteger, unique=True)
    # Tebeosfera no tiene IDs numéricos como Comic Vine/AniList: identifica
    # sus fichas por slug de texto (p.ej. "thorgal_1981_distrinovel").
    tebeosfera_slug: Mapped[str|None] = mapped_column(String(255), unique=True)
    # GCD (C0, descubrimiento — ver docs/adr/0002-enricher-scope.md): sí
    # tiene IDs numéricos, igual que Comic Vine/AniList.
    gcd_id:          Mapped[int|None] = mapped_column(BigInteger, unique=True)
    cover_url:       Mapped[str|None] = mapped_column(String(500))
    metadata_:       Mapped[dict]     = mapped_column("metadata", JSONB, default=dict)
    metadata_source: Mapped[str|None] = mapped_column(String(20))
    # H2 (peer review v2): último intento de enriquecimiento, con o sin
    # match. NULL = nunca intentado. El enricher solo reintenta series con
    # NULL o con más de 30 días — antes reintentaba en CADA ciclo para
    # siempre a las que nunca encontraban fuente, quemando rate limit.
    enrichment_attempted_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    # H3 (peer review v2): ver Creator.locked_fields.
    locked_fields:   Mapped[list]     = mapped_column(ARRAY(String), default=list)
    created_at:      Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at:      Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    publisher: Mapped["Publisher|None"]  = relationship(back_populates="series")
    issues:    Mapped[list["Issue"]]     = relationship(back_populates="series", cascade="all, delete-orphan")
    genres:    Mapped[list["Genre"]]     = relationship(secondary=series_genres)


class StoryArc(Base):
    __tablename__ = "story_arcs"
    id:            Mapped[str]      = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    title:         Mapped[str]      = mapped_column(String(500), nullable=False)
    description:   Mapped[str|None] = mapped_column(Text)
    is_crossover:  Mapped[bool]     = mapped_column(Boolean, default=False)
    universe_id:   Mapped[str|None] = mapped_column(UUID(as_uuid=True), ForeignKey("universes.id", ondelete="SET NULL"))
    comic_vine_id: Mapped[int|None] = mapped_column(BigInteger, unique=True)
    metadata_:     Mapped[dict]     = mapped_column("metadata", JSONB, default=dict)
    created_at:    Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    universe:   Mapped["Universe|None"]          = relationship(back_populates="story_arcs")
    arc_issues: Mapped[list["StoryArcIssue"]]    = relationship(back_populates="story_arc", cascade="all, delete-orphan")


class Issue(Base):
    __tablename__ = "issues"
    __table_args__ = (UniqueConstraint("series_id", "issue_number", "volume"),)
    id:              Mapped[str]          = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    series_id:       Mapped[str]          = mapped_column(UUID(as_uuid=True), ForeignKey("series.id", ondelete="CASCADE"), nullable=False)
    issue_number:    Mapped[str|None]     = mapped_column(String(20))
    volume:          Mapped[int]          = mapped_column(Integer, default=1)
    title:           Mapped[str|None]     = mapped_column(String(500))
    release_date:    Mapped[date|None]    = mapped_column(Date)
    format:          Mapped[IssueFormat]  = mapped_column(Enum(IssueFormat, name="issue_format", values_callable=lambda obj: [e.value for e in obj]), default=IssueFormat.SINGLE_ISSUE)
    page_count:      Mapped[int|None]     = mapped_column(Integer)
    isbn:            Mapped[str|None]     = mapped_column(String(20))
    synopsis:        Mapped[str|None]     = mapped_column(Text)
    cover_url:       Mapped[str|None]     = mapped_column(String(500))
    comic_vine_id:   Mapped[int|None]     = mapped_column(BigInteger, unique=True)
    sort_order:      Mapped[float|None]   = mapped_column(Float)
    metadata_:       Mapped[dict]         = mapped_column("metadata", JSONB, default=dict)
    metadata_source: Mapped[str|None]     = mapped_column(String(20))
    # H2/H3 (peer review v2): ver Series.enrichment_attempted_at / Creator.locked_fields.
    enrichment_attempted_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    locked_fields:   Mapped[list]         = mapped_column(ARRAY(String), default=list)
    created_at:      Mapped[datetime]     = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at:      Mapped[datetime]     = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    series:           Mapped["Series"]               = relationship(back_populates="issues")
    credits:          Mapped[list["IssueCreator"]]   = relationship(back_populates="issue", cascade="all, delete-orphan")
    files:            Mapped[list["File"]]            = relationship(back_populates="issue")
    characters:       Mapped[list["Character"]]       = relationship(secondary=issue_characters)
    tags:             Mapped[list["Tag"]]              = relationship(secondary=issue_tags)
    reading_progress: Mapped["ReadingProgress|None"]  = relationship(back_populates="issue", uselist=False)


class IssueCreator(Base):
    __tablename__ = "issue_creators"
    issue_id:   Mapped[str]         = mapped_column(UUID(as_uuid=True), ForeignKey("issues.id", ondelete="CASCADE"), primary_key=True)
    creator_id: Mapped[str]         = mapped_column(UUID(as_uuid=True), ForeignKey("creators.id", ondelete="CASCADE"), primary_key=True)
    role:       Mapped[CreatorRole] = mapped_column(Enum(CreatorRole, name="creator_role", values_callable=lambda obj: [e.value for e in obj]), primary_key=True)
    issue:   Mapped["Issue"]   = relationship(back_populates="credits")
    creator: Mapped["Creator"] = relationship(back_populates="issue_credits")


class StoryArcIssue(Base):
    __tablename__ = "story_arc_issues"
    story_arc_id:  Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("story_arcs.id", ondelete="CASCADE"), primary_key=True)
    issue_id:      Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("issues.id", ondelete="CASCADE"), primary_key=True)
    reading_order: Mapped[int] = mapped_column(Integer, nullable=False)
    story_arc: Mapped["StoryArc"] = relationship(back_populates="arc_issues")
    issue:     Mapped["Issue"]    = relationship()


class Tag(Base):
    __tablename__ = "tags"
    id:    Mapped[str]      = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name:  Mapped[str]      = mapped_column(String(100), unique=True, nullable=False)
    color: Mapped[str|None] = mapped_column(String(7))


class File(Base):
    __tablename__ = "files"
    id:                  Mapped[str]          = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    issue_id:            Mapped[str|None]     = mapped_column(UUID(as_uuid=True), ForeignKey("issues.id", ondelete="SET NULL"))
    file_path:           Mapped[str]          = mapped_column(String(1000), unique=True, nullable=False)
    file_name:           Mapped[str]          = mapped_column(String(500), nullable=False)
    file_format:         Mapped[FileFormat]   = mapped_column(Enum(FileFormat, name="file_format", values_callable=lambda obj: [e.value for e in obj]), nullable=False)
    file_size_bytes:     Mapped[int|None]     = mapped_column(BigInteger)
    sha256_hash:         Mapped[str|None]     = mapped_column(String(64), index=True)
    source_tag:          Mapped[str|None]     = mapped_column(String(50))
    width_px:            Mapped[int|None]     = mapped_column(Integer)
    covered_issue_ids:   Mapped[list]         = mapped_column(ARRAY(UUID(as_uuid=True)), default=list)
    quality:             Mapped[str|None]     = mapped_column(String(50))
    is_verified:         Mapped[bool]         = mapped_column(Boolean, default=False)
    metadata_source:     Mapped[str|None]     = mapped_column(String(20))
    imported_at:         Mapped[datetime]     = mapped_column(DateTime(timezone=True), server_default=func.now())
    metadata_:           Mapped[dict]         = mapped_column("metadata", JSONB, default=dict)
    # B2: el coleccionista descartó este archivo desde la bandeja de
    # pendientes ("ignorar"). Distinto de tener issue_id — un archivo
    # puede seguir sin issue_id (posible hueco del enricher) sin haber
    # sido nunca revisado ni descartado a mano.
    review_dismissed:    Mapped[bool]         = mapped_column(Boolean, default=False, server_default="false")
    issue: Mapped["Issue|None"] = relationship(back_populates="files")


class Wishlist(Base):
    __tablename__ = "wishlist"
    __table_args__ = (CheckConstraint("series_id IS NOT NULL OR issue_id IS NOT NULL", name="wishlist_target_check"),)
    id:               Mapped[str]             = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    series_id:        Mapped[str|None]        = mapped_column(UUID(as_uuid=True), ForeignKey("series.id", ondelete="CASCADE"))
    issue_id:         Mapped[str|None]        = mapped_column(UUID(as_uuid=True), ForeignKey("issues.id", ondelete="CASCADE"))
    status:           Mapped[WishlistStatus]  = mapped_column(Enum(WishlistStatus, name="wishlist_status", values_callable=lambda obj: [e.value for e in obj]), default=WishlistStatus.WANTED)
    priority:         Mapped[int]             = mapped_column(Integer, default=5)
    search_query:     Mapped[str|None]        = mapped_column(String(500))
    added_at:         Mapped[datetime]        = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_searched_at: Mapped[datetime|None]   = mapped_column(DateTime(timezone=True))
    downloaded_at:    Mapped[datetime|None]   = mapped_column(DateTime(timezone=True))
    notes:            Mapped[str|None]        = mapped_column(Text)
    # D1: solo observabilidad (qué backend, qué hash) — no participan en
    # detectar si algo terminó; eso lo hace Orchestrator.check_completions
    # comprobando si ya existe un File enlazado, agnóstico de backend.
    download_ref:     Mapped[str|None]        = mapped_column(String(255))
    download_backend: Mapped[str|None]        = mapped_column(String(20))
    series: Mapped["Series|None"] = relationship()
    issue:  Mapped["Issue|None"]  = relationship()


class ReadingProgress(Base):
    __tablename__ = "reading_progress"
    id:           Mapped[str]           = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    issue_id:     Mapped[str]           = mapped_column(UUID(as_uuid=True), ForeignKey("issues.id", ondelete="CASCADE"), unique=True, nullable=False)
    status:       Mapped[ReadingStatus] = mapped_column(Enum(ReadingStatus, name="reading_status", values_callable=lambda obj: [e.value for e in obj]), default=ReadingStatus.UNREAD)
    current_page: Mapped[int]           = mapped_column(Integer, default=0)
    rating:       Mapped[int|None]      = mapped_column(SmallInteger)
    started_at:   Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    notes:        Mapped[str|None]      = mapped_column(Text)
    issue: Mapped["Issue"] = relationship(back_populates="reading_progress")


class ReadingList(Base):
    __tablename__ = "reading_lists"
    id:          Mapped[str]      = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name:        Mapped[str]      = mapped_column(String(255), nullable=False)
    description: Mapped[str|None] = mapped_column(Text)
    created_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    items: Mapped[list["ReadingListItem"]] = relationship(back_populates="reading_list", cascade="all, delete-orphan")


class ImportRun(Base):
    """Un ciclo de Importer.scan_and_import(). Persistido para poder
    responder "¿qué pasó en el ciclo de las 03:00?" desde una futura UI
    sin depender solo de los logs (idea rescatada de zascarr: scrape_runs)."""
    __tablename__ = "import_runs"
    id:              Mapped[str]      = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    started_at:      Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at:     Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    files_scanned:   Mapped[int]      = mapped_column(Integer, default=0)
    imported_count:  Mapped[int]      = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int]      = mapped_column(Integer, default=0)
    unsorted_count:  Mapped[int]      = mapped_column(Integer, default=0)
    error_count:     Mapped[int]      = mapped_column(Integer, default=0)
    # {"imported": [...], "duplicates": [...], "unsorted": [...], "errors": [...]}
    # — cada entrada es una línea legible, no un objeto estructurado: este
    # informe está pensado para mostrarse tal cual, no para consultarse campo
    # a campo (para eso ya están los contadores de arriba).
    details:         Mapped[dict]     = mapped_column(JSONB, default=dict)


class ReadingListItem(Base):
    __tablename__ = "reading_list_items"
    reading_list_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("reading_lists.id", ondelete="CASCADE"), primary_key=True)
    issue_id:        Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("issues.id", ondelete="CASCADE"), primary_key=True)
    position:        Mapped[int] = mapped_column(Integer, nullable=False)
    reading_list: Mapped["ReadingList"] = relationship(back_populates="items")
    issue:        Mapped["Issue"]       = relationship()


class LegalAcknowledgment(Base):
    """Blindaje legal: sin user_id — ZascArr es de un solo operador,
    sin autenticación. "¿Aceptado?" es "¿existe una fila con
    legal_version == la versión actual?" (hash de LEGAL.md, ver
    services/legal.py), no un estado por usuario."""
    __tablename__ = "legal_acknowledgments"
    id:            Mapped[str]      = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    accepted_at:   Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    legal_version: Mapped[str]      = mapped_column(String(64), nullable=False)
