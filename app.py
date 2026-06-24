"""
Flask 应用入口
"""

import os

# 设置 Hugging Face 镜像 (国内加速)，必须在 import transformers 之前设置
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

# 修复 Windows 下 PyTorch 加载 c10.dll/fbgemm.dll 时的 [WinError 1114] 冲突报错
os.environ['KMP_DUPLICATE_LIB_OK'] = 'True'

from flask import Flask, render_template, redirect, url_for, jsonify
from flask_cors import CORS
from flask_login import LoginManager, current_user
from config import Config
from models import db
from models.user import User
from routes import register_routes


def create_app():
    """创建 Flask 应用"""
    app = Flask(__name__)
    app.config.from_object(Config)

    # 初始化扩展
    db.init_app(app)
    CORS(app, supports_credentials=True) # 允许跨域请求

    # 登录管理
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = "page_login"

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    @login_manager.unauthorized_handler
    def unauthorized():
        from flask import request

        if request.path.startswith("/api/"):
            from flask import jsonify

            return jsonify({"code": 401, "message": "请先登录"}), 401
        return redirect(url_for("page_login"))

    # 注册路由蓝图 **
    register_routes(app)

    # 禁用缓存，强制前端获取最新 JS (修复页面不刷新的问题)
    @app.after_request
    def add_header(response):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    # 页面路由
    @app.route("/")
    def index():
        if current_user.is_authenticated:
            return render_template("index.html")
        return redirect(url_for("page_login"))

    @app.route("/login")
    def page_login():
        if current_user.is_authenticated:
            return redirect(url_for("index"))
        return render_template("login.html")

    @app.route("/admin", strict_slashes=False)
    def admin_page():
        print(current_user) 
        if not current_user.is_authenticated:
            return redirect(url_for("page_login"))
        if not current_user.is_admin:
            return redirect(url_for("index"))

        return render_template("admin.html")

    @app.route("/dashboard", strict_slashes=False)
    def dashboard_page():
        if not current_user.is_authenticated:
            return redirect(url_for("page_login"))
        if not current_user.is_admin:
            return redirect(url_for("index"))

        return render_template("dashboard.html")

    # 确保上传目录存在
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # 错误处理
    @app.errorhandler(413)
    def request_entity_too_large(error):
        return jsonify({"code": 413, "message": "文件太大，请上传小于16MB的文件"}), 413

    @app.errorhandler(500)
    def internal_server_error(error):
        return jsonify({"code": 500, "message": "服务器内部错误"}), 500
    return app


if __name__ == "__main__":
    app = create_app()
    
    with app.app_context():
        db.create_all()
    app.run(debug=True, host="0.0.0.0", port=5000, use_reloader=False)
