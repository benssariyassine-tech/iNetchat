import os
from flask import Flask, jsonify, render_template, send_from_directory, request
from flask_cors import CORS
from supabase import create_client, Client

app = Flask(__name__, template_folder='templates', static_folder='static')
CORS(app)

# ====== Supabase Connection ======
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if SUPABASE_URL and SUPABASE_KEY:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    supabase = None
    print("⚠️ Supabase credentials not configured!")


# ====== Routes ======
@app.route('/')
def home():
    return render_template('index.html')


@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({
        "status": "ok",
        "app": "iNetchat",
        "supabase": "connected" if supabase else "not configured"
    })


@app.route('/api/db-test', methods=['GET'])
def db_test():
    if not supabase:
        return jsonify({"status": "error", "message": "Supabase not configured"}), 500
    try:
        response = supabase.table('profiles').select('*').limit(1).execute()
        return jsonify({
            "status": "success",
            "message": "Database connected successfully!",
            "data": response.data
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ====== AUTH: Sign Up ======
@app.route('/api/auth/signup', methods=['POST'])
def signup():
    if not supabase:
        return jsonify({"error": "Supabase not configured"}), 500
    
    data = request.get_json()
    email = data.get('email', '').strip()
    password = data.get('password', '')
    username = data.get('username', '').strip()
    display_name = data.get('display_name', '').strip()
    
    if not email or not password or not username:
        return jsonify({"error": "كل الحقول مطلوبة"}), 400
    
    if len(password) < 6:
        return jsonify({"error": "كلمة المرور لازم 6 أحرف على الأقل"}), 400
    
    try:
        # 1. إنشاء المستخدم في Supabase Auth
        auth_response = supabase.auth.sign_up({
            "email": email,
            "password": password
        })
        
        if not auth_response.user:
            return jsonify({"error": "فشل إنشاء الحساب"}), 400
        
        user_id = auth_response.user.id
        
        # 2. إنشاء البروفايل في جدول profiles
        profile_data = {
            "id": user_id,
            "username": username,
            "display_name": display_name or username,
            "avatar_url": None,
            "bio": None,
            "is_private": False
        }
        
        profile_response = supabase.table('profiles').insert(profile_data).execute()
        
        return jsonify({
            "status": "success",
            "message": "تم إنشاء الحساب بنجاح!",
            "user": {
                "id": user_id,
                "email": email,
                "username": username
            }
        }), 201
        
    except Exception as e:
        error_msg = str(e)
        if "already registered" in error_msg.lower() or "already exists" in error_msg.lower():
            return jsonify({"error": "هذا الإيميل مستعمل من قبل"}), 400
        return jsonify({"error": error_msg}), 500


# ====== AUTH: Login ======
@app.route('/api/auth/login', methods=['POST'])
def login():
    if not supabase:
        return jsonify({"error": "Supabase not configured"}), 500
    
    data = request.get_json()
    email = data.get('email', '').strip()
    password = data.get('password', '')
    
    if not email or not password:
        return jsonify({"error": "الإيميل وكلمة المرور مطلوبين"}), 400
    
    try:
        auth_response = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        
        if not auth_response.user:
            return jsonify({"error": "إيميل أو كلمة مرور غالطين"}), 401
        
        # جيب البروفايل
        profile = supabase.table('profiles').select('*').eq('id', auth_response.user.id).execute()
        
        return jsonify({
            "status": "success",
            "message": "تم تسجيل الدخول!",
            "user": {
                "id": auth_response.user.id,
                "email": auth_response.user.email,
                "access_token": auth_response.session.access_token if auth_response.session else None
            },
            "profile": profile.data[0] if profile.data else None
        })
        
    except Exception as e:
        error_msg = str(e)
        if "invalid" in error_msg.lower() or "credentials" in error_msg.lower():
            return jsonify({"error": "إيميل أو كلمة مرور غالطين"}), 401
        return jsonify({"error": error_msg}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
