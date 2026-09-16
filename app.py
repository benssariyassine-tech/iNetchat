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
    return jsonify({"status": "ok", "app": "iNetchat",
                    "supabase": "connected" if supabase else "not configured"})


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
        auth_response = supabase.auth.sign_up({"email": email, "password": password})
        if not auth_response.user:
            return jsonify({"error": "فشل إنشاء الحساب"}), 400
        user_id = auth_response.user.id
        supabase.table('profiles').insert({
            "id": user_id, "username": username,
            "display_name": display_name or username,
            "avatar_url": None, "bio": None, "is_private": False
        }).execute()
        return jsonify({"status": "success", "message": "تم إنشاء الحساب بنجاح!",
                        "user": {"id": user_id, "email": email, "username": username}}), 201
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
        auth_response = supabase.auth.sign_in_with_password({"email": email, "password": password})
        if not auth_response.user:
            return jsonify({"error": "إيميل أو كلمة مرور غالطين"}), 401
        profile = supabase.table('profiles').select('*').eq('id', auth_response.user.id).execute()
        return jsonify({
            "status": "success", "message": "تم تسجيل الدخول!",
            "user": {"id": auth_response.user.id, "email": auth_response.user.email,
                     "access_token": auth_response.session.access_token if auth_response.session else None},
            "profile": profile.data[0] if profile.data else None
        })
    except Exception as e:
        if "invalid" in str(e).lower():
            return jsonify({"error": "إيميل أو كلمة مرور غالطين"}), 401
        return jsonify({"error": str(e)}), 500


# ====== USERS: List all (except me) ======
@app.route('/api/users', methods=['GET'])
def get_users():
    if not supabase:
        return jsonify({"error": "Supabase not configured"}), 500
    my_id = request.args.get('me', '')
    try:
        if my_id:
            response = supabase.table('profiles').select('*').neq('id', my_id).limit(50).execute()
        else:
            response = supabase.table('profiles').select('*').limit(50).execute()
        return jsonify({"status": "success", "users": response.data})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ====== USERS: Search by username or email ======
@app.route('/api/users/search', methods=['GET'])
def search_users():
    if not supabase:
        return jsonify({"error": "Supabase not configured"}), 500
    q = request.args.get('q', '').strip()
    my_id = request.args.get('me', '')
    if not q:
        return jsonify({"users": []})
    try:
        response = supabase.table('profiles').select('*').ilike('username', f'%{q}%').limit(20).execute()
        users = [u for u in response.data if u['id'] != my_id]
        return jsonify({"status": "success", "users": users})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ====== CHATS: Create or get 1-on-1 chat ======
@app.route('/api/chats/create', methods=['POST'])
def create_chat():
    if not supabase:
        return jsonify({"error": "Supabase not configured"}), 500
    data = request.get_json()
    user1 = data.get('user1')
    user2 = data.get('user2')
    if not user1 or not user2:
        return jsonify({"error": "معلومات ناقصة"}), 400
    try:
        # ابحث عن دردشة موجودة بيناتهم
        existing = supabase.table('chats').select('*').eq('is_group', False).execute()
        for c in existing.data:
            members = supabase.table('chat_members').select('user_id').eq('chat_id', c['id']).execute()
            member_ids = [m['user_id'] for m in members.data]
            if set(member_ids) == {user1, user2}:
                return jsonify({"status": "existing", "chat_id": c['id']})
        # أنشئ دردشة جديدة
        chat = supabase.table('chats').insert({
            "is_group": False, "created_by": user1
        }).execute()
        chat_id = chat.data[0]['id']
        supabase.table('chat_members').insert([
            {"chat_id": chat_id, "user_id": user1},
            {"chat_id": chat_id, "user_id": user2}
        ]).execute()
        return jsonify({"status": "created", "chat_id": chat_id}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ====== MESSAGES: Get by chat ======
@app.route('/api/messages/<chat_id>', methods=['GET'])
def get_messages(chat_id):
    if not supabase:
        return jsonify({"error": "Supabase not configured"}), 500
    try:
        response = supabase.table('messages').select('*').eq('chat_id', chat_id).order('created_at').execute()
        return jsonify({"status": "success", "messages": response.data})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ====== MESSAGES: Send ======
@app.route('/api/messages/send', methods=['POST'])
def send_message():
    if not supabase:
        return jsonify({"error": "Supabase not configured"}), 500
    data = request.get_json()
    chat_id = data.get('chat_id')
    sender_id = data.get('sender_id')
    content = data.get('content', '').strip()
    if not chat_id or not sender_id or not content:
        return jsonify({"error": "معلومات ناقصة"}), 400
    try:
        response = supabase.table('messages').insert({
            "chat_id": chat_id, "sender_id": sender_id,
            "content": content, "message_type": "text"
        }).execute()
        return jsonify({"status": "success", "message": response.data[0]}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
