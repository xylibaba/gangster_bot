import socketio
from aiohttp import web
import json
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.future import select
from database import ServerBase, User, ServerMessage
import bcrypt
import os

# Database setup
# For PostgreSQL use: postgresql+asyncpg://user:password@host/dbname
DATABASE_URL = "sqlite+aiosqlite:///server.db" 
engine = create_async_engine(DATABASE_URL, echo=True)
async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

sio = socketio.AsyncServer(async_mode='aiohttp', cors_allowed_origins='*')
app = web.Application()
sio.attach(app)

# Helper to get user by username
async def get_user(session, username):
    result = await session.execute(select(User).where(User.username == username))
    return result.scalars().first()

@sio.event
async def connect(sid, environ):
    print(f"Client connected: {sid}")

@sio.event
async def disconnect(sid):
    print(f"Client disconnected: {sid}")

@sio.event
async def register(sid, data):
    username = data['username']
    password = data['password']
    public_key = data['public_key']
    
    async with async_session() as session:
        existing_user = await get_user(session, username)
        if existing_user:
            return {'status': 'error', 'message': 'Username already exists'}
        
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        new_user = User(username=username, password_hash=hashed_password, public_key=public_key)
        session.add(new_user)
        await session.commit()
        return {'status': 'success', 'message': 'Registered successfully'}

@sio.event
async def login(sid, data):
    username = data['username']
    password = data['password']
    
    async with async_session() as session:
        user = await get_user(session, username)
        if not user or not bcrypt.checkpw(password.encode('utf-8'), user.password_hash.encode('utf-8')):
            return {'status': 'error', 'message': 'Invalid credentials'}
        
        # Store session info
        await sio.save_session(sid, {'user_id': user.id, 'username': user.username})
        sio.enter_room(sid, user.username)
        return {'status': 'success', 'message': 'Logged in', 'public_key': user.public_key}

@sio.event
async def send_message(sid, data):
    session_data = await sio.get_session(sid)
    if not session_data:
        return {'status': 'error', 'message': 'Not authenticated'}
    
    sender_id = session_data['user_id']
    sender_username = session_data['username']
    receiver_username = data['receiver']
    content = data['content'] # Encrypted
    
    async with async_session() as session:
        receiver = await get_user(session, receiver_username)
        if not receiver:
            return {'status': 'error', 'message': 'User not found'}
        
        message = ServerMessage(sender_id=sender_id, receiver_id=receiver.id, content=content)
        session.add(message)
        await session.commit()
        
        await sio.emit('new_message', {
            'sender': sender_username,
            'content': content,
            'timestamp': str(message.timestamp)
        }, room=receiver_username)
        
        return {'status': 'success'}

@sio.event
async def get_public_key(sid, data):
    username = data['username']
    async with async_session() as session:
        user = await get_user(session, username)
        if user:
            return {'status': 'success', 'public_key': user.public_key}
        return {'status': 'error', 'message': 'User not found'}

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(ServerBase.metadata.create_all)

if __name__ == '__main__':
    # Initialize DB before starting server
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(init_db())
    
    web.run_app(app, port=5000)
