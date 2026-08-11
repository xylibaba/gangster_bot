from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

ServerBase = declarative_base()
ClientBase = declarative_base()

# Server Models
class User(ServerBase):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    public_key = Column(Text, nullable=False) # PEM format

class ServerMessage(ServerBase):
    __tablename__ = 'messages'
    id = Column(Integer, primary_key=True)
    sender_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    receiver_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    content = Column(Text, nullable=False) # Encrypted content
    timestamp = Column(DateTime, default=datetime.utcnow)

    sender = relationship("User", foreign_keys=[sender_id])
    receiver = relationship("User", foreign_keys=[receiver_id])

# Client Models (Local storage)
class Contact(ClientBase):
    __tablename__ = 'contacts'
    id = Column(Integer, primary_key=True) # Server ID
    username = Column(String, unique=True, nullable=False)
    public_key = Column(Text, nullable=False)

class ClientMessage(ClientBase):
    __tablename__ = 'messages'
    id = Column(Integer, primary_key=True, autoincrement=True)
    server_id = Column(Integer, nullable=True) # ID on server
    sender_username = Column(String, nullable=False)
    receiver_username = Column(String, nullable=False)
    content = Column(Text, nullable=False) # Decrypted content
    timestamp = Column(DateTime, default=datetime.utcnow)
    is_sent = Column(Boolean, default=False)
