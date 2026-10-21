"""
Database Models using SQLAlchemy
Real database persistence for all data
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from sqlalchemy import create_engine, func, inspect, text, Column, String, Float, Integer, DateTime, Text, JSON, ForeignKey, Table, Index
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from config import DATABASE_URL, DB_TYPE, DB_POOL_SIZE, DB_MAX_OVERFLOW, DB_POOL_RECYCLE

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    """Naive UTC timestamp (datetime.utcnow() is deprecated since Python 3.12)"""
    return datetime.now(timezone.utc).replace(tzinfo=None)

Base = declarative_base()

# ============================================================================
# ASSOCIATION TABLES
# ============================================================================

wardrobe_similarity = Table(
    'wardrobe_similarity',
    Base.metadata,
    Column('wardrobe_id', String, ForeignKey('wardrobe_items.id')),
    Column('product_id', String, ForeignKey('products.id'))
)

# ============================================================================
# PRODUCT MODEL
# ============================================================================

class Product(Base):
    """Represents a clothing product in the database"""
    __tablename__ = "products"

    id = Column(String(50), primary_key=True, unique=True)
    name = Column(String(255), nullable=False)
    brand = Column(String(100), nullable=True)
    category = Column(String(50), nullable=False)
    subcategory = Column(String(50), nullable=True)

    # Physical attributes
    primary_color = Column(String(50), nullable=True)
    secondary_colors = Column(JSON, nullable=True)  # List of colors
    color_hex = Column(String(7), nullable=True)  # Hex color code
    material = Column(String(100), nullable=True)
    materials_list = Column(JSON, nullable=True)  # Multiple materials

    # Style & use
    style = Column(String(50), nullable=True)  # casual, formal, sporty, etc
    season = Column(String(50), nullable=True)  # spring, summer, fall, winter
    use_case = Column(String(100), nullable=True)  # casual, office, sports, etc

    # Sizing & care
    size_range = Column(JSON, nullable=True)  # Available sizes
    care_instructions = Column(Text, nullable=True)
    durability_score = Column(Float, default=0.5)  # 0-1
    sustainability_rating = Column(Float, default=0.5)  # 0-1

    # Pricing & value
    price = Column(Float, nullable=True)
    currency = Column(String(3), default="USD")
    resale_value_estimate = Column(Float, nullable=True)

    # Media
    image_url = Column(Text, nullable=True)
    image_base64 = Column(Text, nullable=True)  # For local storage
    thumbnail_url = Column(Text, nullable=True)

    # Description & metadata
    description = Column(Text, nullable=True)
    tags = Column(JSON, nullable=True)  # List of tags
    related_products = Column(JSON, nullable=True)  # List of related product IDs

    # AI/ML data
    embedding = Column(JSON, nullable=True)  # CLIP embedding (list)
    embedding_dimension = Column(Integer, default=512)

    # Metadata
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
    source = Column(String(100), nullable=True)  # "seed" = loaded from the catalog JSON
    data_source = Column(String(100), nullable=True)  # original dataset / API (real catalog)
    source_license = Column(String(50), nullable=True)
    source_url = Column(Text, nullable=True)
    gender = Column(String(20), nullable=True)

    # Relationships
    wardrobe_items = relationship("WardrobeItem", secondary=wardrobe_similarity, back_populates="similar_products")

# ============================================================================
# WARDROBE ITEM MODEL
# ============================================================================

class WardrobeItem(Base):
    """User's wardrobe item"""
    __tablename__ = "wardrobe_items"

    id = Column(String(50), primary_key=True, unique=True)
    user_id = Column(String(50), nullable=True, index=True)
    product_id = Column(String(50), ForeignKey('products.id'), nullable=True)

    # Item details
    name = Column(String(255), nullable=False)
    category = Column(String(50), nullable=False)
    color = Column(String(50), nullable=True)
    size = Column(String(10), nullable=True)
    style = Column(String(50), nullable=True)
    material = Column(String(100), nullable=True)
    use_case = Column(String(100), nullable=True)
    season = Column(String(50), nullable=True)
    brand = Column(String(100), nullable=True)
    price = Column(Float, nullable=True)

    # Image (file served from /uploads or the catalog image) + its CLIP embedding
    image_url = Column(Text, nullable=True)
    image_base64 = Column(Text, nullable=True)
    image_embedding = Column(JSON, nullable=True)

    # Status
    condition = Column(String(50), default="good")  # good, fair, worn
    is_archived = Column(Integer, default=0)

    # Metadata
    purchase_date = Column(DateTime, nullable=True)
    purchase_price = Column(Float, nullable=True)
    added_to_wardrobe = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    # Relationships
    similar_products = relationship("Product", secondary=wardrobe_similarity, back_populates="wardrobe_items")
    analyses = relationship("SimilarityAnalysis", back_populates="wardrobe_item")
    feedback = relationship("UserFeedback", back_populates="wardrobe_item")

# ============================================================================
# SIMILARITY ANALYSIS MODEL
# ============================================================================

class SimilarityAnalysis(Base):
    """Results of analyzing a new item against wardrobe"""
    __tablename__ = "similarity_analyses"

    id = Column(String(50), primary_key=True, unique=True)
    wardrobe_item_id = Column(String(50), ForeignKey('wardrobe_items.id'), nullable=True)
    user_id = Column(String(50), nullable=True, index=True)

    # Analyzed item (the candidate purchase)
    new_item = Column(JSON, nullable=True)

    # Similarity results
    similar_items = Column(JSON, nullable=True)  # List of {id, name, similarity}
    visual_similarity = Column(Float, default=0.0)
    functional_similarity = Column(Float, default=0.0)
    category_saturation = Column(Float, default=0.0)

    # Scores
    redundancy_score = Column(Float, default=0.0)  # 0-100
    outfit_contribution_score = Column(Float, default=0.0)  # 0-100
    recommendation = Column(String(50), default="consider")  # buy, consider, skip

    # Explanations
    explanation = Column(Text, nullable=True)
    explanation_source = Column(String(20), nullable=True)  # openai | claude | rules
    alternatives = Column(JSON, nullable=True)  # Suggested alternatives

    # Confidence
    confidence = Column(Float, default=0.0)  # 0-1

    # Execution
    execution_time_ms = Column(Float, nullable=True)
    agent_iterations = Column(Integer, default=0)

    # Metadata
    created_at = Column(DateTime, default=_utcnow, index=True)
    analyzed_at = Column(DateTime, default=_utcnow)

    # Relationships
    wardrobe_item = relationship("WardrobeItem", back_populates="analyses")

# ============================================================================
# USER FEEDBACK MODEL
# ============================================================================

class UserFeedback(Base):
    """Track user feedback for model improvement"""
    __tablename__ = "user_feedback"

    id = Column(String(50), primary_key=True, unique=True)
    wardrobe_item_id = Column(String(50), ForeignKey('wardrobe_items.id'), nullable=True)
    item_id = Column(String(50), nullable=True)  # analysis id, product id or wardrobe item id
    user_id = Column(String(50), nullable=True)

    # Feedback type
    feedback_type = Column(String(50))  # "helpful", "inaccurate", "missing_info", etc
    rating = Column(Integer, default=0)  # 0-5 stars
    comment = Column(Text, nullable=True)

    # What was feedback about
    feedback_on = Column(String(100), nullable=True)  # feature that was wrong/good

    # Impact
    helped_decision = Column(Integer, default=0)  # 0=no, 1=yes

    # Metadata
    created_at = Column(DateTime, default=_utcnow)

    # Relationships
    wardrobe_item = relationship("WardrobeItem", back_populates="feedback")

# ============================================================================
# EXECUTION LOG MODEL
# ============================================================================

class ExecutionLog(Base):
    """Log all system executions for debugging & monitoring"""
    __tablename__ = "execution_logs"

    id = Column(String(50), primary_key=True, unique=True)
    user_id = Column(String(50), nullable=True)

    # What happened
    event_type = Column(String(100))  # "analysis", "upload", "feedback", etc
    feature_id = Column(Integer, nullable=True)  # Which feature executed

    # Status
    status = Column(String(50))  # "success", "error", "pending"
    message = Column(Text, nullable=True)

    # Timing
    started_at = Column(DateTime, default=_utcnow)
    ended_at = Column(DateTime, nullable=True)
    duration_ms = Column(Float, nullable=True)

    # Details
    input_data = Column(JSON, nullable=True)
    output_data = Column(JSON, nullable=True)
    error_details = Column(Text, nullable=True)

    # Metadata
    created_at = Column(DateTime, default=_utcnow)

# ============================================================================
# USERS & CLIENT ANALYTICS
# ============================================================================

class User(Base):
    """Account (email + PBKDF2 password hash). Anonymous visitors use the 'local' guest wardrobe."""
    __tablename__ = "users"

    id = Column(String(50), primary_key=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(100), nullable=True)
    # Profile - adapts the starter wardrobe, the catalog and the sizes of the pieces
    gender = Column(String(12), nullable=True)            # Women | Men | Unspecified
    clothing_size = Column(String(5), nullable=True)      # XS ... XXL
    shoe_size = Column(String(5), nullable=True)          # EU size
    style_preferences = Column(JSON, nullable=True)       # ["casual", "sporty", ...]
    favorite_colors = Column(JSON, nullable=True)         # ["black", "navy", ...]
    created_at = Column(DateTime, default=_utcnow)
    last_login = Column(DateTime, nullable=True)


class ClientEvent(Base):
    """Product analytics sent by the frontend (page views, actions) - no personal data"""
    __tablename__ = "client_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), nullable=True, index=True)
    session_id = Column(String(64), nullable=True)
    name = Column(String(64), nullable=False)
    page = Column(String(64), nullable=True)
    properties = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=_utcnow, index=True)

    __table_args__ = (Index("ix_client_events_name_created", "name", "created_at"),)

# ============================================================================
# DATABASE MANAGER
# ============================================================================

class DatabaseManager:
    """Manages all database operations"""

    def __init__(self):
        # Create engine
        if DB_TYPE == "postgresql":
            engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=DB_POOL_SIZE,
                                   max_overflow=DB_MAX_OVERFLOW, pool_recycle=DB_POOL_RECYCLE)
        else:  # sqlite
            engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
        self.engine = engine
        self.dialect = engine.dialect.name

        # Create all tables, then add columns / indexes introduced after the database was created
        Base.metadata.create_all(engine)
        self._add_missing_columns(engine)
        self._add_missing_indexes(engine)
        with engine.begin() as conn:  # rows written before accounts existed belong to the guest
            conn.execute(text("UPDATE similarity_analyses SET user_id = 'local' WHERE user_id IS NULL"))

        # Create session factory
        self.SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    @staticmethod
    def _add_missing_columns(engine) -> None:
        """Minimal auto-migration: ALTER TABLE ADD COLUMN for model columns missing in an existing table"""
        inspector = inspect(engine)
        with engine.begin() as conn:
            for table in Base.metadata.sorted_tables:
                if not inspector.has_table(table.name):
                    continue
                existing = {c["name"] for c in inspector.get_columns(table.name)}
                for column in table.columns:
                    if column.name not in existing:
                        col_type = column.type.compile(engine.dialect)
                        conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN "{column.name}" {col_type}'))
                        logger.info(f"Migrated: added column {table.name}.{column.name}")

    @staticmethod
    def _add_missing_indexes(engine) -> None:
        for table in Base.metadata.sorted_tables:
            for index in table.indexes:
                index.create(engine, checkfirst=True)

    def ping(self) -> bool:
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.error(f"Database ping failed: {e}")
            return False

    def get_session(self):
        """Get a new database session"""
        return self.SessionLocal()

    @staticmethod
    def init_db():
        """Initialize database with all tables"""
        manager = DatabaseManager()
        return manager

    # --------
    # PRODUCTS
    # --------

    PRODUCT_FIELDS = {c.name for c in Product.__table__.columns}

    def seed_products(self, seed_file: Path) -> int:
        """Sync the products table with the catalog JSON: insert new, update changed, remove stale seed rows"""
        with open(seed_file, "r", encoding="utf-8") as f:
            products = json.load(f)

        with self.get_session() as session:
            existing = {p.id: p for p in session.query(Product).filter(Product.source == "seed").all()}
            seed_ids = set()
            inserted = 0
            for p in products:
                fields = {k: v for k, v in p.items() if k in self.PRODUCT_FIELDS}
                seed_ids.add(fields["id"])
                row = existing.get(fields["id"])
                if row is None:
                    session.add(Product(**fields, source="seed"))
                    inserted += 1
                else:
                    for k, v in fields.items():
                        setattr(row, k, v)
            stale = [pid for pid in existing if pid not in seed_ids]
            if stale:
                session.query(Product).filter(Product.id.in_(stale)).delete(synchronize_session=False)
            session.commit()
            if inserted or stale:
                logger.info(f"Catalog sync: {inserted} inserted, {len(stale)} removed")
            return session.query(func.count(Product.id)).scalar()

    # --------
    # WARDROBE (single local user)
    # --------

    WARDROBE_FIELDS = ("id", "product_id", "name", "category", "color", "style", "material", "use_case",
                       "season", "brand", "price", "size", "condition", "image_url")

    def _wardrobe_dict(self, item: "WardrobeItem", with_embedding: bool = False) -> Dict:
        data = {f: getattr(item, f) for f in self.WARDROBE_FIELDS}
        data["added_at"] = item.added_to_wardrobe.isoformat() if item.added_to_wardrobe else None
        if with_embedding:
            data["image_embedding"] = item.image_embedding
        return data

    def list_wardrobe(self, user_id: str = "local", with_embedding: bool = False,
                      limit: Optional[int] = None, offset: int = 0) -> List[Dict]:
        with self.get_session() as session:
            query = (session.query(WardrobeItem)
                     .filter(WardrobeItem.user_id == user_id, WardrobeItem.is_archived == 0)
                     .order_by(WardrobeItem.added_to_wardrobe, WardrobeItem.id))
            if offset:
                query = query.offset(offset)
            if limit is not None:
                query = query.limit(limit)
            return [self._wardrobe_dict(i, with_embedding) for i in query.all()]

    def count_wardrobe(self, user_id: str = "local") -> int:
        with self.get_session() as session:
            return (session.query(func.count(WardrobeItem.id))
                    .filter(WardrobeItem.user_id == user_id, WardrobeItem.is_archived == 0).scalar())

    def wardrobe_value(self, user_id: str = "local") -> float:
        with self.get_session() as session:
            total = (session.query(func.sum(WardrobeItem.price))
                     .filter(WardrobeItem.user_id == user_id, WardrobeItem.is_archived == 0).scalar())
            return round(float(total or 0), 2)

    def add_wardrobe_item(self, item: Dict, user_id: str = "local") -> Dict:
        allowed = {c.name for c in WardrobeItem.__table__.columns}
        with self.get_session() as session:
            row = WardrobeItem(**{k: v for k, v in item.items() if k in allowed}, user_id=user_id)
            session.add(row)
            session.commit()
            return self._wardrobe_dict(row)

    def delete_wardrobe_item(self, item_id: str, user_id: str = "local") -> Optional[Dict]:
        with self.get_session() as session:
            row = session.get(WardrobeItem, item_id)
            if not row or row.user_id != user_id:
                return None
            data = self._wardrobe_dict(row)
            session.delete(row)
            session.commit()
            return data

    def update_wardrobe_item(self, item_id: str, changes: Dict, user_id: str = "local") -> Optional[Dict]:
        editable = {"name", "category", "color", "style", "material", "use_case", "season", "brand", "price", "size", "condition"}
        with self.get_session() as session:
            row = session.get(WardrobeItem, item_id)
            if not row or row.user_id != user_id:
                return None
            for key, value in changes.items():
                if key in editable:
                    setattr(row, key, value)
            session.commit()
            return self._wardrobe_dict(row)

    def clear_wardrobe(self, user_id: str = "local") -> int:
        with self.get_session() as session:
            count = session.query(WardrobeItem).filter(WardrobeItem.user_id == user_id).delete()
            session.commit()
            return count

    def load_products(self) -> List[Dict]:
        """Return the whole catalog as plain dicts"""
        with self.get_session() as session:
            return [
                {c: getattr(p, c) for c in self.PRODUCT_FIELDS if c not in ("created_at", "updated_at", "embedding")}
                for p in session.query(Product).all()
            ]

    def count_products(self) -> int:
        with self.get_session() as session:
            return session.query(func.count(Product.id)).scalar()

    # --------
    # ANALYSES & FEEDBACK
    # --------

    def save_analysis(self, analysis_id: str, new_item: Dict, result: Dict, user_id: str = "local") -> None:
        with self.get_session() as session:
            session.add(SimilarityAnalysis(
                id=analysis_id,
                user_id=user_id,
                explanation_source=result.get("explanation_source"),
                new_item=new_item,
                similar_items=result.get("similar_items"),
                visual_similarity=result.get("visual_similarity", 0.0),
                functional_similarity=result.get("functional_similarity", 0.0),
                category_saturation=result.get("category_saturation", 0.0),
                redundancy_score=result.get("redundancy_score", 0.0),
                outfit_contribution_score=result.get("outfit_contribution", 0.0),
                recommendation=result.get("recommendation"),
                explanation=result.get("explanation"),
                alternatives=result.get("alternatives"),
                confidence=result.get("confidence", 0.0),
                execution_time_ms=result.get("execution_time_ms"),
            ))
            session.commit()

    def get_analysis(self, analysis_id: str, user_id: Optional[str] = None) -> Optional[Dict]:
        with self.get_session() as session:
            a = session.get(SimilarityAnalysis, analysis_id)
            if not a or (user_id is not None and a.user_id != user_id):
                return None
            return {
                "analysis_id": a.id,
                "new_item": a.new_item,
                "similar_items": a.similar_items,
                "redundancy_score": a.redundancy_score,
                "recommendation": a.recommendation,
                "explanation": a.explanation,
                "confidence": a.confidence,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }

    def save_feedback(self, feedback_id: str, feedback: Dict, user_id: str = "local") -> None:
        with self.get_session() as session:
            session.add(UserFeedback(
                id=feedback_id,
                user_id=user_id,
                item_id=feedback.get("item_id"),
                feedback_type=feedback.get("feedback_type"),
                rating=feedback.get("rating", 0),
                comment=feedback.get("comment"),
                feedback_on=feedback.get("feedback_on"),
                helped_decision=1 if feedback.get("helped_decision") else 0,
            ))
            session.commit()

    def feedback_summary(self) -> Dict:
        with self.get_session() as session:
            count, avg = session.query(func.count(UserFeedback.id), func.avg(UserFeedback.rating)).one()
            return {"total_feedback": count, "average_rating": round(float(avg), 2) if avg is not None else None}

    def count_analyses(self, user_id: Optional[str] = None) -> int:
        with self.get_session() as session:
            query = session.query(func.count(SimilarityAnalysis.id))
            if user_id is not None:
                query = query.filter(SimilarityAnalysis.user_id == user_id)
            return query.scalar()

    def list_analyses(self, limit: int = 10, offset: int = 0, user_id: str = "local") -> List[Dict]:
        """Most recent analyses (history)"""
        with self.get_session() as session:
            rows = (session.query(SimilarityAnalysis).filter(SimilarityAnalysis.user_id == user_id)
                    .order_by(SimilarityAnalysis.created_at.desc(), SimilarityAnalysis.id)
                    .offset(offset).limit(limit).all())
            return [{
                "analysis_id": a.id,
                "name": (a.new_item or {}).get("name"),
                "category": (a.new_item or {}).get("category"),
                "color": (a.new_item or {}).get("color"),
                "price": (a.new_item or {}).get("price"),
                "image_url": (a.new_item or {}).get("image_url"),
                "redundancy_score": a.redundancy_score,
                "recommendation": a.recommendation,
                "explanation_source": a.explanation_source,
                "top_match": (a.similar_items or [{}])[0].get("name") if a.similar_items else None,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            } for a in rows]

    def savings_summary(self, user_id: str = "local") -> Dict:
        """Purchases the app advised to skip, and the money they represent"""
        with self.get_session() as session:
            skipped = (session.query(SimilarityAnalysis)
                       .filter(SimilarityAnalysis.recommendation == "skip", SimilarityAnalysis.user_id == user_id).all())
            money = sum(float((a.new_item or {}).get("price") or 0) for a in skipped)
            return {"duplicates_avoided": len(skipped), "money_saved": round(money, 2)}

    def log_execution(self, log_id: str, event_type: str, status: str, duration_ms: float,
                      feature_id: Optional[int] = None, message: Optional[str] = None) -> None:
        try:
            with self.get_session() as session:
                session.add(ExecutionLog(
                    id=log_id, event_type=event_type, status=status, feature_id=feature_id,
                    message=message, duration_ms=duration_ms, ended_at=_utcnow(),
                ))
                session.commit()
        except Exception as e:  # logging must never break a request
            logger.warning(f"Could not write execution log: {e}")

    # --------
    # USERS
    # --------

    PROFILE_FIELDS = ("gender", "clothing_size", "shoe_size", "style_preferences", "favorite_colors")

    @classmethod
    def _user_dict(cls, user: "User") -> Dict:
        return {"id": user.id, "email": user.email, "display_name": user.display_name,
                **{f: getattr(user, f) for f in cls.PROFILE_FIELDS},
                "created_at": user.created_at.isoformat() if user.created_at else None}

    def create_user(self, user_id: str, email: str, password_hash: str, display_name: Optional[str],
                    profile: Optional[Dict] = None) -> Optional[Dict]:
        """None when the email is already registered"""
        from sqlalchemy.exc import IntegrityError

        with self.get_session() as session:
            user = User(id=user_id, email=email, password_hash=password_hash, display_name=display_name,
                        **{k: v for k, v in (profile or {}).items() if k in self.PROFILE_FIELDS})
            session.add(user)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                return None
            return self._user_dict(user)

    def get_user_credentials(self, email: str) -> Optional[Dict]:
        with self.get_session() as session:
            user = session.query(User).filter(User.email == email).one_or_none()
            return dict(self._user_dict(user), password_hash=user.password_hash) if user else None

    def get_user(self, user_id: str) -> Optional[Dict]:
        with self.get_session() as session:
            user = session.get(User, user_id)
            return self._user_dict(user) if user else None

    def update_user(self, user_id: str, changes: Dict) -> Optional[Dict]:
        with self.get_session() as session:
            user = session.get(User, user_id)
            if not user:
                return None
            for key, value in changes.items():
                if key in self.PROFILE_FIELDS or key == "display_name":
                    setattr(user, key, value)
            session.commit()
            return self._user_dict(user)

    def touch_login(self, user_id: str) -> None:
        with self.get_session() as session:
            user = session.get(User, user_id)
            if user:
                user.last_login = _utcnow()
                session.commit()

    def count_users(self) -> int:
        with self.get_session() as session:
            return session.query(func.count(User.id)).scalar()

    def claim_guest_data(self, user_id: str) -> Dict:
        """Move the guest wardrobe and history to an account (offered right after sign-up)"""
        with self.get_session() as session:
            items = (session.query(WardrobeItem).filter(WardrobeItem.user_id == "local")
                     .update({WardrobeItem.user_id: user_id}, synchronize_session=False))
            analyses = (session.query(SimilarityAnalysis).filter(SimilarityAnalysis.user_id == "local")
                        .update({SimilarityAnalysis.user_id: user_id}, synchronize_session=False))
            session.commit()
            return {"wardrobe_items": items, "analyses": analyses}

    # --------
    # ANALYTICS
    # --------

    def save_client_events(self, events: List[Dict], user_id: str, session_id: Optional[str]) -> int:
        with self.get_session() as session:
            session.add_all([ClientEvent(user_id=user_id, session_id=session_id, name=e["name"],
                                         page=e.get("page"), properties=e.get("properties")) for e in events])
            session.commit()
            return len(events)

    def analytics_summary(self, user_id: Optional[str], days: int) -> Dict:
        """Business analytics over the last `days` days - one user, or everyone when user_id is None"""
        from datetime import timedelta

        since = _utcnow() - timedelta(days=days)
        with self.get_session() as session:
            def scoped(query, column):
                return query.filter(column == user_id) if user_id is not None else query

            rows = scoped(session.query(SimilarityAnalysis).filter(SimilarityAnalysis.created_at >= since),
                          SimilarityAnalysis.user_id).all()
            verdicts = {"buy": 0, "consider": 0, "skip": 0}
            timeline: Dict[str, Dict[str, int]] = {}
            categories: Dict[str, int] = {}
            sources: Dict[str, int] = {}
            money_saved, durations = 0.0, []
            for a in rows:
                verdict = a.recommendation if a.recommendation in verdicts else "consider"
                verdicts[verdict] += 1
                day = a.created_at.date().isoformat()
                timeline.setdefault(day, {"buy": 0, "consider": 0, "skip": 0})[verdict] += 1
                category = (a.new_item or {}).get("category") or "unknown"
                categories[category] = categories.get(category, 0) + 1
                source = a.explanation_source or "rules"
                sources[source] = sources.get(source, 0) + 1
                if verdict == "skip":
                    money_saved += float((a.new_item or {}).get("price") or 0)
                if a.execution_time_ms is not None:
                    durations.append(a.execution_time_ms)

            events = scoped(session.query(ClientEvent.name, func.count(ClientEvent.id))
                            .filter(ClientEvent.created_at >= since), ClientEvent.user_id) \
                .group_by(ClientEvent.name).all()
            pages = scoped(session.query(ClientEvent.page, func.count(ClientEvent.id))
                           .filter(ClientEvent.created_at >= since, ClientEvent.name == "page_view"), ClientEvent.user_id) \
                .group_by(ClientEvent.page).all()
            feedback = scoped(session.query(func.count(UserFeedback.id), func.avg(UserFeedback.rating))
                              .filter(UserFeedback.created_at >= since), UserFeedback.user_id).one()

            durations.sort()
            return {
                "days": days,
                "analyses": len(rows),
                "average_score": round(sum(a.redundancy_score or 0 for a in rows) / len(rows), 1) if rows else None,
                "verdicts": verdicts,
                "timeline": [{"date": d, **counts} for d, counts in sorted(timeline.items())],
                "categories": dict(sorted(categories.items(), key=lambda kv: -kv[1])),
                "explanation_sources": sources,
                "money_saved": round(money_saved, 2),
                "analysis_time_ms": {
                    "p50": round(durations[len(durations) // 2], 1) if durations else None,
                    "p95": round(durations[min(len(durations) - 1, int(len(durations) * 0.95))], 1) if durations else None,
                },
                "events": {name: count for name, count in events},
                "page_views": {page or "?": count for page, count in pages},
                "feedback": {"count": feedback[0],
                             "average_rating": round(float(feedback[1]), 2) if feedback[1] is not None else None},
            }

# ============================================================================
# INITIALIZATION
# ============================================================================

if __name__ == "__main__":
    from config import SEED_DATA_FILE

    db = DatabaseManager.init_db()
    total = db.seed_products(SEED_DATA_FILE)
    print("✅ Database initialized successfully!")
    print(f"   Database URL: {DATABASE_URL}")
    print(f"   Tables: {', '.join(sorted(Base.metadata.tables))}")
    print(f"   Products in database: {total}")
