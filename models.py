from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()

class User(Base):
    """User model for storing user information."""
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<User(telegram_id={self.telegram_id}, username={self.username})>"

class CompressionJob(Base):
    """Compression job model for storing video compression jobs."""
    __tablename__ = 'compression_jobs'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    original_file_name = Column(String, nullable=True)
    original_file_size = Column(Float, nullable=True)  # Size in MB
    compressed_file_size = Column(Float, nullable=True)  # Size in MB
    compression_ratio = Column(Float, nullable=True)  # percentage of size reduction
    status = Column(String, default='pending')  # pending, processing, completed, failed, canceled
    created_at = Column(DateTime, default=func.now())
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    processing_time = Column(Float, nullable=True)  # Time in seconds
    error_message = Column(String, nullable=True)
    
    def __repr__(self):
        return f"<CompressionJob(id={self.id}, user_id={self.user_id}, status={self.status})>"

class UserPreference(Base):
    """User preference model for storing user preferences."""
    __tablename__ = 'user_preferences'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), unique=True, nullable=False)
    resolution = Column(String, default='480p')  # 480p, 720p, etc.
    quality = Column(String, default='medium')  # low, medium, high
    notifications_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    def __repr__(self):
        return f"<UserPreference(user_id={self.user_id}, resolution={self.resolution}, quality={self.quality})>"