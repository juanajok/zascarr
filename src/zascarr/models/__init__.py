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
    Index,
    Integer,
    SmallInteger,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
    text,
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


# B15 (2026-09-26): qué Issue.format corresponde a cada marcador de edición que
# naming.py extrae del nombre de archivo. Vive aquí (junto al enum) y no en un
# servicio, porque lo comparten el camino manual (ReviewService.assign_to_series)
# y el automático (SeriesMatcher), y ninguno de los dos puede importar del otro
# sin ciclo. Todo lo que no sea un marcador de edición es una grapa suelta.
EDITION_KIND_A_FORMAT: dict[str, IssueFormat] = {
    "omnigold": IssueFormat.OMNIBUS,
    "integral": IssueFormat.OMNIBUS,
    "tomo": IssueFormat.TRADE_PAPERBACK,
    "volumen": IssueFormat.TRADE_PAPERBACK,
}

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
    #: D8: un deseo que la política generó y que ya no se quiere (p.ej. el
    #: coleccionista pasó la serie a `ninguno`). NO se borra — deja constancia
    #: de que existió y de que se dejó de buscar a propósito. Distinto de
    #: FAILED: aquí no falló nada.
    RETIRADO    = "retirado"


class WishlistPolicy(str, enum.Enum):
    """D8: qué números de una serie busca ZascArr **por su cuenta**.

    No silencia nunca un item añadido a mano: gobierna lo que se **genera**.
    """
    NONE    = "ninguno"      # por defecto, y lo que deja la migración 0015
    MISSING = "faltantes"    # los que faltan, según `huecos_de_serie`
    FUTURE  = "futuros"      # reservado: NO computable todavía (ver ficha D8)
    ALL     = "todos"        # reservado: no se ofrece hasta que D3 lo defina


class WishlistOrigin(str, enum.Enum):
    """D8: de dónde salió el item.

    `manual` = lo pidió el coleccionista (nunca se toca solo).
    `politica` = lo generó ZascArr a partir de `Series.wishlist_policy`.
    """
    MANUAL  = "manual"
    POLICY  = "politica"

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
    # D8: qué números de esta serie busca ZascArr por su cuenta. `ninguno` por
    # defecto y para las series ya existentes (migración 0015): sin opt-in
    # explícito no se genera ni se busca nada nuevo.
    wishlist_policy: Mapped[WishlistPolicy] = mapped_column(
        Enum(WishlistPolicy, name="wishlist_policy",
             values_callable=lambda obj: [e.value for e in obj]),
        nullable=False, default=WishlistPolicy.NONE, server_default=WishlistPolicy.NONE.value)
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
    # Integridad (ficha benchmark-integridad-hash-dedupe): hash del fichero
    # TAL COMO SE IMPORTÓ, antes de la primera reescritura por B6 — escribir
    # ComicInfo.xml cambia los bytes, así que `sha256_hash` deja de valer para
    # reconocer el original cuando vuelve a llegar. El dedupe busca por
    # `sha256_hash` O `original_sha256`; se fija la primera vez que B6 reemplaza
    # un CBZ y nunca se sobrescribe. NULL = no reescrito aún (o era CBR/PDF).
    original_sha256:     Mapped[str|None]     = mapped_column(String(64), index=True)
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
    # B7: si el fichero desaparece del disco (borrado a mano fuera de
    # ZascArr) deja de "contar como que lo tienes" sin que nadie tenga
    # que avisar — Importer.scan_and_import() lo detecta en cada ciclo
    # (ver Importer._detectar_desaparecidos). Se revierte solo si el
    # fichero reaparece (disco de red que estuvo desmontado, etc.) — el
    # File nunca se borra por esto, solo se marca.
    is_missing:          Mapped[bool]         = mapped_column(Boolean, default=False, server_default="false")
    missing_since:       Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    issue: Mapped["Issue|None"] = relationship(back_populates="files")


class AsignacionEstado(str, enum.Enum):
    """Estados PERSISTIDOS de una operación de asignación (ADR 0006, migración 0017).

    Son solo cuatro. Los RESULTADOS que el servicio devuelve al cliente no son estados. Los RECUPERABLES
    (`pendiente`, `reparacion_pendiente`, `asignado_limpieza_pendiente`) dejan la operación `preparada` o
    `confirmada`, es decir, VIVA, con su reserva intacta: una reparación pendiente no debe liberar el destino
    por accidente. `destino_ocupado`, en cambio, CANCELA la operación y libera la reserva (el reintento
    reserva el siguiente nombre libre)."""
    PREPARADA = "preparada"      # reservada; el origen sigue siendo la única copia confirmada
    CONFIRMADA = "confirmada"    # la BD ya apunta al destino; falta (o falló) retirar el origen
    LIMPIADA = "limpiada"        # terminada: el origen se retiró
    CANCELADA = "cancelada"      # abandonada sin efecto (p. ej. el destino lo ocupó un ajeno)


#: Estados que RESERVAN archivo y destino (índices únicos parciales). Fuente única: la migración 0017 y
#: las pruebas comparan contra esta constante.
ASIGNACION_ESTADOS_VIVOS = (AsignacionEstado.PREPARADA, AsignacionEstado.CONFIRMADA)
_VIVOS_SQL = "estado IN ('preparada', 'confirmada')"


class AsignacionOperacion(Base):
    """Una asignación de un archivo a una serie y número, recuperable tras un fallo (ADR 0006)."""
    __tablename__ = "asignacion_operaciones"
    __table_args__ = (
        CheckConstraint(
            "estado IN ('limpiada', 'cancelada') OR (file_id IS NOT NULL AND series_id IS NOT NULL)",
            name="ck_asignacion_viva_con_referencias"),
        CheckConstraint("origen <> destino AND temporal <> destino AND temporal <> origen",
                        name="ck_asignacion_rutas_distintas"),
        CheckConstraint("size_bytes >= 0", name="ck_asignacion_tamano"),
        CheckConstraint("epoca >= 0", name="ck_asignacion_epoca"),
        CheckConstraint("length(btrim(issue_number)) > 0", name="ck_asignacion_issue_number"),
        CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="ck_asignacion_sha256"),
        Index("uq_asignacion_viva_por_archivo", "file_id", unique=True,
              postgresql_where=text(_VIVOS_SQL)),
        Index("uq_asignacion_viva_por_destino", "destino", unique=True,
              postgresql_where=text(_VIVOS_SQL)),
        Index("ix_asignacion_viva_creada", "creada", postgresql_where=text(_VIVOS_SQL)),
        # Declarados a mano (no `index=True`, que los llamaría `ix_asignacion_operaciones_*`): mismos nombres
        # que la migración 0017, para que Alembic no proponga renombrarlos.
        Index("ix_asignacion_file_id", "file_id"),
        Index("ix_asignacion_series_id", "series_id"),
    )
    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4,
                                    server_default=text("gen_random_uuid()"))
    # SET NULL + el CHECK de arriba: borrar un archivo/serie con una operación VIVA falla; con una cerrada
    # procede y la fila queda como historial.
    file_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("files.id", ondelete="SET NULL"))
    series_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("series.id", ondelete="SET NULL"))
    estado: Mapped[AsignacionEstado] = mapped_column(
        Enum(AsignacionEstado, name="asignacion_estado",
             values_callable=lambda obj: [e.value for e in obj]),
        nullable=False, default=AsignacionEstado.PREPARADA,
        server_default=AsignacionEstado.PREPARADA.value)
    origen: Mapped[str] = mapped_column(String(1000), nullable=False)
    destino: Mapped[str] = mapped_column(String(1000), nullable=False)   # el EFECTIVO, no el canónico
    temporal: Mapped[str] = mapped_column(String(1000), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mtime_ns: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    issue_number: Mapped[str] = mapped_column(String(20), nullable=False)
    formato: Mapped[IssueFormat] = mapped_column(
        Enum(IssueFormat, name="issue_format",
             values_callable=lambda obj: [e.value for e in obj]),
        nullable=False)
    aprender_alias: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True,
                                                 server_default="true")
    # Ficha de vallado: cada ejecutor que toma la operación la incrementa; sus escrituras llevan `AND epoca = <la suya>`.
    epoca: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    creada: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actualizada: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AltaEstado(enum.StrEnum):
    """Estado de una operación de alta de serie (migración 0018). `creada`: la confirmación
    creó la serie; `deshecha`: el deshacer la borró y esa operación **no puede volver a
    crearla**."""
    CREADA = "creada"
    DESHECHA = "deshecha"


class AltaOperacion(Base):
    """Comprobante de una operación de alta de la superficie de revisión (rebanada 2b, 0018).

    **No es un historial de auditoría**: existe para reconocer un reintento del mismo token
    (devolver el mismo resultado) y para que un reintento atrasado NO revierta un «deshacer».
    Se purga pasadas 24 h **y** una vez caducado el token. Guarda lo mínimo —sin token, sesión
    ni credenciales— y **`series_id` no es una clave foránea**: borrar la serie no debe borrar
    su comprobante (con `CASCADE` el reintento volvería a crearla)."""
    __tablename__ = "alta_operaciones"
    __table_args__ = (Index("ix_alta_operaciones_purga", "creada"),)
    operacion_id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    series_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False)
    estado: Mapped[AltaEstado] = mapped_column(
        Enum(AltaEstado, name="alta_estado", values_callable=lambda obj: [e.value for e in obj]),
        nullable=False)
    token_hasta: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    creada: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    actualizada: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)


class VinculacionOperacion(Base):
    """Informe INMUTABLE de una vinculación en su sitio (rebanada 2d, migración 0019).

    Se escribe una sola vez, en la misma transacción que los vínculos (un disparador de la
    migración rechaza todo `UPDATE`). **No es un historial de auditoría**: sirve para devolver
    el mismo resultado ante un reintento, también tras un reinicio, y se purga pasadas 24 h
    **y** caducado el token. Sin token, sesión, rutas, nombres ni hash. `series_id` no es
    clave foránea: borrar la serie no borra el informe."""
    __tablename__ = "vinculacion_operaciones"
    __table_args__ = (Index("ix_vinculacion_operaciones_purga", "creada"),)
    operacion_id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    series_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False)
    resultado: Mapped[dict] = mapped_column(JSONB, nullable=False)
    token_hasta: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    creada: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)


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
    # D8: de dónde salió este item. `manual` para todo lo que ya existía
    # (migración 0015): la retirada de items de política NUNCA puede tocar lo
    # que pidió el coleccionista.
    origen: Mapped[WishlistOrigin] = mapped_column(
        Enum(WishlistOrigin, name="wishlist_origen",
             values_callable=lambda obj: [e.value for e in obj]),
        nullable=False, default=WishlistOrigin.MANUAL,
        server_default=WishlistOrigin.MANUAL.value)
    # D8: número pedido, cuando el item lo pide por número. Es INTEGER a
    # propósito: así `04` y `4` son el mismo valor por construcción (el matcher
    # ya tuvo un bug de ceros: el issue #0 no encontraba nunca su fila), y el
    # índice único parcial puede ser una comparación de enteros. NULL = item de
    # serie o manual sin número.
    numero: Mapped[int|None] = mapped_column(Integer)
    # D9: por qué la última pasada del orquestador no avanzó (texto en
    # español, para la UI) — nunca secretos ni cuerpos HTTP completos.
    # Sin timestamp propio: se correlaciona con last_searched_at, ya
    # marcado en el mismo punto donde se decide la causa.
    last_error:       Mapped[str|None]        = mapped_column(Text)
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
    # B7: ficheros ya en biblioteca que dejaron de existir en disco desde
    # el ciclo anterior — no cuenta llegadas nuevas (eso es imported_count).
    disappeared_count: Mapped[int]    = mapped_column(Integer, default=0, server_default="0")
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


class RuntimeSetting(Base):
    """D11: ajustes de integraciones (Comic Vine, Prowlarr, Transmission,
    aMule) editables desde /ui/ajustes, sin editar .env ni reiniciar.

    Fila única (id=1 fijo, mismo patrón singleton que
    LegalAcknowledgment pero con una sola fila en vez de "la más
    reciente"): un JSONB con solo los campos que el coleccionista
    cambió alguna vez desde la UI. NO es una segunda fuente de verdad
    de configuración — config.py/.env siguen declarando todos los
    campos, tipos y valores por defecto (CLAUDE.md §2); esto es
    exclusivamente el override en caliente que services/
    runtime_settings.py aplica sobre el Settings ya cacheado."""
    __tablename__ = "runtime_settings"
    id:         Mapped[int]      = mapped_column(Integer, primary_key=True, default=1)
    values:     Mapped[dict]     = mapped_column(JSONB, default=dict, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class LocalAlias(Base):
    """B13: patrón de nombre → serie, aprendido de asignaciones manuales
    en Pendientes (ReviewService.assign_to_series). SeriesMatcher.decide()
    lo consulta ANTES del matcher fuzzy — si el coleccionista ya corrigió
    a mano un patrón una vez, no debe volver a preguntarse.

    Alias LOCAL de esta instalación, nunca una regla global (CLAUDE.md
    §5, "el sistema gestiona, nunca facilita"): pattern_norm es
    core.matcher.normalize_title(título extraído por naming.py del
    nombre de archivo original), no un regex ni nada exportable."""
    __tablename__ = "local_aliases"
    id:           Mapped[str]      = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    pattern_norm: Mapped[str]      = mapped_column(String(500), nullable=False, unique=True)
    series_id:    Mapped[str]      = mapped_column(UUID(as_uuid=True), ForeignKey("series.id", ondelete="CASCADE"), nullable=False)
    created_at:   Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
