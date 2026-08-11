import sys
import socketio
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QLineEdit, QPushButton, QTextEdit, QListWidget, QStackedWidget, QMessageBox, QInputDialog)
from PyQt6.QtCore import QThread, pyqtSignal, QObject, Qt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import ClientBase, Contact, ClientMessage
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import serialization, hashes
import os
import base64

# Database setup
DATABASE_URL = "sqlite:///client.db"
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

def init_db():
    ClientBase.metadata.create_all(engine)

# Encryption helpers
def generate_keys():
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    public_key = private_key.public_key()
    
    pem_private = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    
    pem_public = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    
    return pem_private, pem_public

def encrypt_message(public_key_pem, message):
    if isinstance(public_key_pem, str):
        public_key_pem = public_key_pem.encode('utf-8')
    public_key = serialization.load_pem_public_key(public_key_pem)
    ciphertext = public_key.encrypt(
        message.encode('utf-8'),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )
    return base64.b64encode(ciphertext).decode('utf-8')

def decrypt_message(private_key_pem, ciphertext_b64):
    if isinstance(private_key_pem, str):
        private_key_pem = private_key_pem.encode('utf-8')
    private_key = serialization.load_pem_private_key(private_key_pem, password=None)
    ciphertext = base64.b64decode(ciphertext_b64)
    plaintext = private_key.decrypt(
        ciphertext,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )
    return plaintext.decode('utf-8')

# Backend Worker
class Backend(QObject):
    message_received = pyqtSignal(dict)
    connection_status = pyqtSignal(bool)
    connection_error = pyqtSignal(str)
    registration_result = pyqtSignal(dict)
    login_result = pyqtSignal(dict)
    public_key_received = pyqtSignal(dict)
    
    def __init__(self):
        super().__init__()
        self.sio = socketio.Client()
        self.sio.on('connect', self.on_connect)
        self.sio.on('disconnect', self.on_disconnect)
        self.sio.on('new_message', self.on_new_message)
        
    def connect_to_server(self, url):
        try:
            self.sio.connect(url)
        except Exception as e:
            self.connection_error.emit(str(e))

    def on_connect(self):
        self.connection_status.emit(True)

    def on_disconnect(self):
        self.connection_status.emit(False)

    def on_new_message(self, data):
        self.message_received.emit(data)

    def register(self, username, password, public_key):
        result = self.sio.call('register', {'username': username, 'password': password, 'public_key': public_key.decode('utf-8')})
        self.registration_result.emit(result)

    def login(self, username, password):
        result = self.sio.call('login', {'username': username, 'password': password})
        self.login_result.emit(result)

    def send_message(self, receiver, content):
        self.sio.emit('send_message', {'receiver': receiver, 'content': content})

    def get_public_key(self, username):
        result = self.sio.call('get_public_key', {'username': username})
        self.public_key_received.emit(result)

# GUI
class MessengerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Secure Messenger")
        self.setGeometry(100, 100, 800, 600)
        
        self.backend = Backend()
        self.backend_thread = QThread()
        self.backend.moveToThread(self.backend_thread)
        self.backend_thread.start()
        
        # Connect signals
        self.backend.connection_status.connect(self.on_connection_status)
        self.backend.connection_error.connect(self.on_connection_error)
        self.backend.registration_result.connect(self.on_registration_result)
        self.backend.login_result.connect(self.on_login_result)
        self.backend.message_received.connect(self.on_message_received)
        self.backend.public_key_received.connect(self.on_public_key_received)
        
        self.init_ui()
        self.is_connected = False
        self.connect_server()
        
        self.current_user = None
        self.private_key = None
        self.current_chat_partner = None

    def init_ui(self):
        self.central_widget = QStackedWidget()
        self.setCentralWidget(self.central_widget)
        
        # Login/Register Screen
        self.auth_widget = QWidget()
        auth_layout = QVBoxLayout()
        
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Username")
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Password")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        
        self.login_btn = QPushButton("Login")
        self.login_btn.clicked.connect(self.do_login)
        self.register_btn = QPushButton("Register")
        self.register_btn.clicked.connect(self.do_register)
        
        auth_layout.addWidget(QLabel("Welcome to Secure Messenger"))
        auth_layout.addWidget(self.username_input)
        auth_layout.addWidget(self.password_input)
        auth_layout.addWidget(self.login_btn)
        auth_layout.addWidget(self.register_btn)
        self.auth_widget.setLayout(auth_layout)
        
        # Main Chat Screen
        self.chat_widget = QWidget()
        chat_layout = QHBoxLayout()
        
        # Contacts List
        contacts_layout = QVBoxLayout()
        self.contacts_list = QListWidget()
        self.contacts_list.itemClicked.connect(self.on_contact_selected)
        self.add_contact_btn = QPushButton("Add Contact")
        self.add_contact_btn.clicked.connect(self.add_contact)
        
        contacts_layout.addWidget(QLabel("Contacts"))
        contacts_layout.addWidget(self.contacts_list)
        contacts_layout.addWidget(self.add_contact_btn)
        
        # Chat Area
        message_layout = QVBoxLayout()
        self.chat_history = QTextEdit()
        self.chat_history.setReadOnly(True)
        
        input_layout = QHBoxLayout()
        self.message_input = QLineEdit()
        self.send_btn = QPushButton("Send")
        self.send_btn.clicked.connect(self.send_message)
        
        input_layout.addWidget(self.message_input)
        input_layout.addWidget(self.send_btn)
        
        message_layout.addWidget(QLabel("Chat"))
        message_layout.addWidget(self.chat_history)
        message_layout.addLayout(input_layout)
        
        chat_layout.addLayout(contacts_layout, 1)
        chat_layout.addLayout(message_layout, 3)
        self.chat_widget.setLayout(chat_layout)
        
        self.central_widget.addWidget(self.auth_widget)
        self.central_widget.addWidget(self.chat_widget)

    def connect_server(self):
        # Run connection in background to avoid freezing UI
        # For simplicity in this example, we call it directly but it might block briefly
        # Ideally, use a signal to trigger connection in the worker thread
        # But since we moved backend to thread, we need to invoke method there
        # We can use QMetaObject.invokeMethod or signals
        # Let's just call it here, as socketio.connect is blocking, we should run it in a separate thread
        # But backend is already in a thread. We need to signal it to connect.
        # For MVP, let's just run it in a separate thread here
        import threading
        threading.Thread(target=self.backend.connect_to_server, args=('http://localhost:5000',)).start()

    def on_connection_status(self, connected):
        self.is_connected = connected
        if connected:
            self.statusBar().showMessage("Connected to server")
        else:
            self.statusBar().showMessage("Disconnected from server")

    def on_connection_error(self, error):
        self.is_connected = False
        self.statusBar().showMessage(f"Connection error: {error}")
        QMessageBox.critical(self, "Connection Error", f"Could not connect to server: {error}")

    def do_register(self):
        if not self.is_connected:
            QMessageBox.warning(self, "Error", "Not connected to server")
            return
        username = self.username_input.text()
        password = self.password_input.text()
        if not username or not password:
            QMessageBox.warning(self, "Error", "Please fill all fields")
            return
        
        # Generate keys
        priv, pub = generate_keys()
        
        # Save keys locally (in a real app, encrypt private key with password)
        with open(f"{username}_private.pem", "wb") as f:
            f.write(priv)
        with open(f"{username}_public.pem", "wb") as f:
            f.write(pub)
            
        self.backend.register(username, password, pub)

    def on_registration_result(self, result):
        if result['status'] == 'success':
            QMessageBox.information(self, "Success", "Registered successfully. Please login.")
        else:
            QMessageBox.warning(self, "Error", result['message'])

    def do_login(self):
        if not self.is_connected:
            QMessageBox.warning(self, "Error", "Not connected to server")
            return
        username = self.username_input.text()
        password = self.password_input.text()
        if not username or not password:
            QMessageBox.warning(self, "Error", "Please fill all fields")
            return
        
        # Load private key
        try:
            with open(f"{username}_private.pem", "rb") as f:
                self.private_key = f.read()
        except FileNotFoundError:
            QMessageBox.warning(self, "Error", "Private key not found. Please register on this device.")
            return

        self.current_user = username
        self.backend.login(username, password)

    def on_login_result(self, result):
        if result['status'] == 'success':
            self.central_widget.setCurrentWidget(self.chat_widget)
            self.load_contacts()
        else:
            QMessageBox.warning(self, "Error", result['message'])

    def add_contact(self):
        username, ok = QInputDialog.getText(self, "Add Contact", "Username:")
        if ok and username:
            self.backend.get_public_key(username)

    def on_public_key_received(self, result):
        if result['status'] == 'success':
            # Save contact
            session = Session()
            # Check if exists
            # For MVP, assume username is unique and just add
            # In real app, handle duplicates
            try:
                contact = Contact(username=result['username'], public_key=result['public_key']) # Wait, result doesn't have username if we called by username?
                # We need to know which username we asked for.
                # The server response should include it or we track it.
                # Let's assume we just add it.
                # Actually, the server response in my server.py only returns public_key.
                # I should update server.py or just use the input from dialog if I could pass it.
                # But I can't pass context easily here without more complex logic.
                # Let's just save it. But wait, I need the username to save it.
                # I'll assume the user entered it correctly and I can't verify it from response unless I change server.
                pass
            except Exception as e:
                print(e)
            
            # For MVP, let's just ask user to confirm or just add it to list
            # I'll modify server to return username in get_public_key response
            pass
            
            # Since I can't easily change server response structure without rewriting server.py (which I can do),
            # I will just use a temporary variable or assume the last added contact is the one.
            # Or better, I will update server.py to return username.
            
            # But wait, I can just add it to the list widget for now and fetch key when sending message if not stored.
            # But better to store it.
            
            # Let's just add to UI list for now.
            # self.contacts_list.addItem(username) # I don't have username here
            pass
        else:
            QMessageBox.warning(self, "Error", result['message'])

    # Let's fix the add contact flow.
    # I will update server.py to return username in get_public_key
    
    def on_contact_selected(self, item):
        self.current_chat_partner = item.text()
        self.chat_history.clear()
        self.load_chat_history()

    def send_message(self):
        if not self.current_chat_partner:
            return
        
        content = self.message_input.text()
        if not content:
            return
            
        # Get partner's public key
        session = Session()
        contact = session.query(Contact).filter_by(username=self.current_chat_partner).first()
        
        if not contact:
            # If not in DB, we need to fetch it.
            # For MVP, let's assume we added it and have the key.
            # If not, we can't encrypt.
            QMessageBox.warning(self, "Error", "Contact public key not found.")
            return

        try:
            encrypted_content = encrypt_message(contact.public_key.encode('utf-8'), content)
            self.backend.send_message(self.current_chat_partner, encrypted_content)
            
            # Save to local DB
            msg = ClientMessage(sender_username=self.current_user, receiver_username=self.current_chat_partner, content=content, is_sent=True)
            session.add(msg)
            session.commit()
            
            self.append_message(f"Me: {content}")
            self.message_input.clear()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Encryption failed: {e}")

    def on_message_received(self, data):
        sender = data['sender']
        encrypted_content = data['content']
        
        try:
            decrypted_content = decrypt_message(self.private_key, encrypted_content)
            
            # Save to DB
            session = Session()
            msg = ClientMessage(sender_username=sender, receiver_username=self.current_user, content=decrypted_content, is_sent=False)
            session.add(msg)
            session.commit()
            
            if self.current_chat_partner == sender:
                self.append_message(f"{sender}: {decrypted_content}")
            else:
                # Notify user
                self.statusBar().showMessage(f"New message from {sender}")
        except Exception as e:
            print(f"Decryption error: {e}")

    def append_message(self, text):
        self.chat_history.append(text)

    def load_contacts(self):
        self.contacts_list.clear()
        session = Session()
        contacts = session.query(Contact).all()
        for contact in contacts:
            self.contacts_list.addItem(contact.username)

    def load_chat_history(self):
        if not self.current_chat_partner:
            return
            
        session = Session()
        messages = session.query(ClientMessage).filter(
            ((ClientMessage.sender_username == self.current_user) & (ClientMessage.receiver_username == self.current_chat_partner)) |
            ((ClientMessage.sender_username == self.current_chat_partner) & (ClientMessage.receiver_username == self.current_user))
        ).order_by(ClientMessage.timestamp).all()
        
        for msg in messages:
            sender = "Me" if msg.sender_username == self.current_user else msg.sender_username
            self.append_message(f"{sender}: {msg.content}")

    # Override add_contact to handle the flow better
    def add_contact(self):
        username, ok = QInputDialog.getText(self, "Add Contact", "Username:")
        if ok and username:
            # We need to fetch the key and then save.
            # Since get_public_key is async via socketio, we need to handle the response.
            # I'll store the pending contact request
            self.pending_contact = username
            self.backend.get_public_key(username)

    def on_public_key_received(self, result):
        if result['status'] == 'success':
            if hasattr(self, 'pending_contact'):
                username = self.pending_contact
                public_key = result['public_key']
                
                session = Session()
                if not session.query(Contact).filter_by(username=username).first():
                    contact = Contact(username=username, public_key=public_key)
                    session.add(contact)
                    session.commit()
                    self.contacts_list.addItem(username)
                    QMessageBox.information(self, "Success", f"Added {username}")
                else:
                    QMessageBox.information(self, "Info", "Contact already exists")
                
                del self.pending_contact
        else:
            QMessageBox.warning(self, "Error", result.get('message', 'Unknown error'))

if __name__ == '__main__':
    init_db()
    app = QApplication(sys.argv)
    window = MessengerApp()
    window.show()
    sys.exit(app.exec())
