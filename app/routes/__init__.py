from .auth import auth_bp
from .dashboard import dashboard_bp
from .notification import notification_bp
from .api import api_bp
from .admin import admin_bp
from .telegram import telegram_bp

# Register all blueprints
def init_routes(app):
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(notification_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(telegram_bp)