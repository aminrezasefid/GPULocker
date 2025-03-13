from flask import Blueprint, session, redirect, url_for, flash
from app.utils.gpu_monitoring import get_gpu_status
api_bp = Blueprint('api', __name__)
@api_bp.route('/api/gpu_status')
def api_gpu_status():
    """API endpoint to get GPU status in JSON format"""
    return get_gpu_status()