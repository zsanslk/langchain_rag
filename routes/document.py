"""
文档管理路由 - 文件上传、列表、删除
"""

import os
import uuid
import hashlib
from flask import Blueprint, request, jsonify, current_app, send_file
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from models import db
from models.document import Document, DocumentChunk
from services.document_service import document_service
from services.embedding_service import embedding_service
from routes.admin import admin_required

document_bp = Blueprint("document", __name__)


@document_bp.route("/upload", methods=["POST"])
@login_required
@admin_required
def upload_file():
    """上传文件（仅管理员）"""
    if "file" not in request.files:
        return jsonify({"code": 400, "message": "没有上传文件"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"code": 400, "message": "文件名为空"}), 400

    if not document_service.allowed_file(file.filename):
        return jsonify({"code": 400, "message": "不支持的文件类型"}), 400

    # 从原始文件名提取扩展名（在 secure_filename 破坏前）
    original_filename = file.filename
    file_ext = document_service.get_file_extension(original_filename)

    if not file_ext:
        return jsonify({"code": 400, "message": "无法识别文件类型"}), 400

    # 保留原始文件名用于展示，用 UUID 生成安全的存储文件名
    display_name = original_filename
    storage_name = f"{current_user.id}_{uuid.uuid4().hex[:8]}.{file_ext}"
    # storage_name = 8_26b14a55.pdf

    # 确保上传目录存在
    upload_folder = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(upload_folder, exist_ok=True)

    # 计算文件 MD5 哈希用于查重
    md5 = hashlib.md5()
    for chunk in file:
        md5.update(chunk)
    file_hash = md5.hexdigest()
    file.seek(0)  # 重置文件指针以便后续保存

    # 查重逻辑：检测是否存在相同哈希的文件
    existing_doc = Document.query.filter_by(file_hash=file_hash).first()
    if existing_doc:
        return (
            jsonify(
                {
                    "code": 400,
                    "message": f'文件已存在 (与 "{existing_doc.file_name}" 内容相同)，请勿重复上传',
                }
            ),
            400,
        )

    file_path = os.path.join(upload_folder, storage_name)

    # 保存文件
    file.save(file_path)
    file_size = os.path.getsize(file_path)

    # 创建文档记录
    doc = Document(
        user_id=current_user.id,
        file_name=display_name,
        file_hash=file_hash,
        file_path=file_path,
        file_type=file_ext,
        file_size=file_size,
        status="processing",
    )
    db.session.add(doc)
    db.session.commit()

    try:
        # 调用 DocumentService 解析文件并递归切片（论文 5.2 节）
        result = document_service.process_document(
            file_path, file_ext, document_id=doc.id
        )
        chunks = result["chunks"]

        if not chunks:
            doc.status = "failed"
            db.session.commit()
            return jsonify({"code": 400, "message": "文件内容为空或无法解析"}), 400

        # 调用 EmbeddingService 向量化并持久化（论文 5.2 节：存储 768 维向量）
        chunk_count = embedding_service.store_chunk_embeddings(doc.id, chunks)

        # 更新文档状态
        doc.chunk_count = chunk_count
        doc.status = "completed"
        db.session.commit()

        return jsonify({"code": 200, "message": "上传成功", "data": doc.to_dict()})

    except Exception as e:
        doc.status = "failed"
        db.session.commit()
        return jsonify({"code": 500, "message": f"文件处理失败: {str(e)}"}), 500


@document_bp.route("/list", methods=["GET"])
@login_required
def list_documents():
    """获取文档列表（所有用户可见）"""
    documents = Document.query.order_by(Document.created_at.desc()).all()

    return jsonify({"code": 200, "data": [doc.to_dict() for doc in documents]})


@document_bp.route("/<int:doc_id>/delete", methods=["DELETE"])
@login_required
@admin_required
def delete_document(doc_id):
    """删除文档（仅管理员）"""
    doc = Document.query.get(doc_id)
    if not doc:
        return jsonify({"code": 404, "message": "文档不存在"}), 404

    # 从 FAISS 持久化索引中移除该文档的所有切片向量
    chunk_ids = [c.id for c in doc.chunks]
    if chunk_ids:
        from services.faiss_store import faiss_store

        faiss_store.remove_vectors(chunk_ids)

    # 删除物理文件
    try:
        if os.path.exists(doc.file_path):
            os.remove(doc.file_path)
    except OSError:
        pass

    # 删除数据库记录（级联删除切片）
    db.session.delete(doc)
    db.session.commit()

    return jsonify({"code": 200, "message": "删除成功"})


@document_bp.route("/<int:doc_id>/file", methods=["GET"])
@login_required
def serve_file(doc_id):
    """获取文档文件内容"""
    doc = Document.query.get(doc_id)
    if not doc:
        return jsonify({"code": 404, "message": "文档不存在"}), 404

    # 处理由于 config 变更导致的路径兼容性问题（绝对路径 vs 相对路径）
    file_path = doc.file_path
    if file_path.startswith("."):
        # 这是一个旧的相对路径 (./uploads/...)
        base_dir = current_app.root_path  # 或者 config['BASE_DIR'] 如果可用
        # app.root_path 通常指向 app.py 所在目录 (langchian310)
        # ./uploads -> langchian310/uploads
        # 需要去掉 ./
        clean_rel_path = file_path[2:] if file_path.startswith("./") else file_path
        file_path = os.path.join(current_app.root_path, clean_rel_path)

    if not os.path.exists(file_path):
        return (
            jsonify({"code": 404, "message": f"文件物理路径不存在: {file_path}"}),
            404,
        )

    # 使用 send_from_directory 更安全
    directory = os.path.dirname(file_path)
    filename = os.path.basename(file_path)

    from flask import send_from_directory

    return send_from_directory(
        directory,
        filename,
        as_attachment=False,
        mimetype="application/pdf" if doc.file_type == "pdf" else "text/plain",
    )


@document_bp.route("/<int:doc_id>/chunks", methods=["GET"])
@login_required
def get_chunks(doc_id):
    """获取文档切片列表"""
    doc = Document.query.get(doc_id)
    if not doc:
        return jsonify({"code": 404, "message": "文档不存在"}), 404

    chunks = (
        DocumentChunk.query.filter_by(document_id=doc_id)
        .order_by(DocumentChunk.chunk_index)
        .all()
    )

    return jsonify(
        {
            "code": 200,
            "data": {
                "doc_name": doc.file_name,
                "chunk_count": doc.chunk_count,
                "chunks": [
                    {"index": c.chunk_index, "content": c.chunk_content} for c in chunks
                ],
            },
        }
    )
