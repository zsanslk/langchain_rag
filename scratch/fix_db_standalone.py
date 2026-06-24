
import pymysql
import os

# 数据库配置
DB_HOST = 'localhost'
DB_PORT = 3306
DB_NAME = 'langchain_db'
DB_USER = 'root'
DB_PASSWORD = 'root'

def fix_database():
    try:
        # 连接数据库
        connection = pymysql.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            port=DB_PORT,
            charset='utf8mb4'
        )
        cursor = connection.cursor()

        # 检查 file_hash 列是否存在
        try:
            cursor.execute("SELECT file_hash FROM documents LIMIT 1")
            print("SUCCESS: 'file_hash' column already exists.")
        except Exception:
            print("INFO: 'file_hash' column missing. Attempting to add it...")
            try:
                # 添加 file_hash 列
                cursor.execute("ALTER TABLE documents ADD COLUMN file_hash VARCHAR(64) DEFAULT NULL")
                # 添加索引
                cursor.execute("CREATE INDEX ix_documents_file_hash ON documents (file_hash)")
                connection.commit()
                print("SUCCESS: Database schema updated successfully.")
            except Exception as e:
                print(f"ERROR: Failed to update database: {e}")
                connection.rollback()
        
        cursor.close()
        connection.close()

    except Exception as e:
        print(f"ERROR: Could not connect to database: {e}")

if __name__ == "__main__":
    fix_database()
