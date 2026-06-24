
import os
from app import create_app
from models import db
from sqlalchemy import text

app = create_app()
with app.app_context():
    try:
        # 尝试查询 file_hash 列是否存在
        db.session.execute(text("SELECT file_hash FROM documents LIMIT 1"))
        print("SUCCESS: 'file_hash' column already exists.")
    except Exception as e:
        print(f"INFO: 'file_hash' column missing or error: {e}")
        print("Attempting to add 'file_hash' column...")
        try:
            db.session.execute(text("ALTER TABLE documents ADD COLUMN file_hash VARCHAR(64) DEFAULT NULL"))
            db.session.execute(text("CREATE INDEX ix_documents_file_hash ON documents (file_hash)"))
            db.session.commit()
            print("SUCCESS: Database schema updated successfully.")
        except Exception as e2:
            print(f"ERROR: Failed to update database: {e2}")
            db.session.rollback()
