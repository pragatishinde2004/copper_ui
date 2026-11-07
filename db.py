from datetime import datetime, time, timedelta
from sqlalchemy import create_engine, event, select, func, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
import config


class Base(DeclarativeBase):
    pass


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime]
    ended_at: Mapped[datetime | None]


class Inspection(Base):
    __tablename__ = "inspections"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"))
    timestamp: Mapped[datetime] = mapped_column(index=True)
    status: Mapped[str]                       # "GOOD" or "DEFECT"
    defect_type: Mapped[str | None]
    confidence: Mapped[float | None]
    image_path: Mapped[str | None]            # relative to DATA_DIR, None if not saved


_Session = None
_engine = None


def _session():
    """Create the engine lazily so the app can start even if the USB is missing."""
    global _Session, _engine
    if _Session is None:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        engine = _engine = create_engine(config.DB_URL)

        @event.listens_for(engine, "connect")
        def _wal(conn, _):
            conn.execute("PRAGMA journal_mode=WAL")   # writer + dashboard reader don't block

        Base.metadata.create_all(engine)
        _Session = sessionmaker(engine)
    return _Session()


def start_run():
    with _session() as s:
        run = Run(started_at=datetime.now())
        s.add(run)
        s.commit()
        return run.id


def end_run(run_id):
    with _session() as s:
        s.get(Run, run_id).ended_at = datetime.now()
        s.commit()


def add_inspection(run_id, ts, status, defect_type, confidence, image_path):
    with _session() as s:
        s.add(Inspection(run_id=run_id, timestamp=ts, status=status,
                         defect_type=defect_type, confidence=confidence,
                         image_path=image_path))
        s.commit()


def counts(day):
    start = datetime.combine(day, time.min)
    with _session() as s:
        rows = s.execute(select(Inspection.status, func.count())
                         .where(Inspection.timestamp >= start)
                         .group_by(Inspection.status)).all()
    d = dict(rows)
    return {"good": d.get("GOOD", 0), "defect": d.get("DEFECT", 0)}


def close():
    """Flush the WAL into the main DB file and release it. Call before shutdown."""
    global _Session, _engine
    if _engine is not None:
        with _engine.connect() as c:
            c.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
        _engine.dispose()
    _Session = _engine = None


def defects_by_day(start, end):
    """Defect count for every date from start to end (inclusive), 0 where none."""
    lo = datetime.combine(start, time.min)
    hi = datetime.combine(end + timedelta(days=1), time.min)
    with _session() as s:
        rows = s.execute(select(func.date(Inspection.timestamp), func.count())
                         .where(Inspection.status == "DEFECT",
                                Inspection.timestamp >= lo, Inspection.timestamp < hi)
                         .group_by(func.date(Inspection.timestamp))).all()
    found = dict(rows)
    return [found.get((start + timedelta(days=i)).isoformat(), 0)
            for i in range((end - start).days + 1)]


def defect_images(day, limit=2):
    """Relative paths of random saved defect images of one day (different on every call)."""
    lo = datetime.combine(day, time.min)
    with _session() as s:
        return list(s.execute(select(Inspection.image_path)
                              .where(Inspection.status == "DEFECT",
                                     Inspection.image_path.is_not(None),
                                     Inspection.timestamp >= lo,
                                     Inspection.timestamp < lo + timedelta(days=1))
                              .order_by(func.random())
                              .limit(limit)).scalars().all())
