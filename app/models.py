from sqlalchemy import BigInteger, Column, Integer, String, ForeignKey, DateTime, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.mutable import MutableDict, MutableList
from datetime import datetime, timezone


Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    
    id = Column(BigInteger, primary_key=True, index=True)
    info = Column(MutableDict.as_mutable(JSON), default=lambda: {})
    data = Column(MutableDict.as_mutable(JSON), default=lambda: {})
    lang = Column(String, default="en")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
                         onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None), nullable=False)
    
    def __repr__(self):
        return f"<User(id={self.id}, data={self.data})>"
    
    
class Music(Base):
    __tablename__ = "musics"
    
    id = Column(String, primary_key=True, index=True)
    title = Column(String, nullable=False)
    artists = Column(MutableList.as_mutable(JSON), default=lambda: {})
    album = Column(MutableDict.as_mutable(JSON), default=lambda: {})
    details = Column(MutableDict.as_mutable(JSON), default=lambda: {})
    photo = Column(String, nullable=False)
    lyrics = Column(String)
    file_id = Column(String)
    
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), 
        nullable=False
    )

    def __repr__(self):
        return f"<Music(id={self.id}, title={self.title})>"


class State(Base):
    __tablename__ = "states"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), unique=True, nullable=False)
    state_data = Column(JSON, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Chat(Base):
    __tablename__ = "chats"
    
    id = Column(BigInteger, primary_key=True, index=True)
    info = Column(MutableDict.as_mutable(JSON), default=lambda: {})
    data = Column(MutableDict.as_mutable(JSON), default=lambda: {})
    admins = Column(MutableList.as_mutable(JSON), default=lambda: [])
    lang = Column(String, default="en")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
                         onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None), nullable=False)
