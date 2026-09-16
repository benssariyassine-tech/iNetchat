import os
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
from supabase import create_client, Client

app = Flask(__name__, template_folder='templates', static_folder='static')
CORS(app)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/api/health')
def health():
    return jsonify({"status": "ok", "supabase": "connected" if supabase else "no"})


# ========== AUTH ==========
@app.route('/api/auth/signup', methods=['POST'])
def signup():
    d = request.get_json()
    email = d.get('email', '').strip()
    password = d.get('password', '')
    username = d.get('username', '').strip()
    display_name = d.get('display_name', '').strip()
    if not email or not password or not username:
        return jsonify({"error": "كل الحقول مطلوبة"}), 400
    if len(password) < 6:
        return jsonify({"error": "كلمة المرور 6 أحرف"}), 400
    try:
        r = supabase.auth.sign_up({"email": email, "password": password})
        if not r.user:
            return jsonify({"error": "فشل الإنشاء"}), 400
        uid = r.user.id
        supabase.table('profiles').insert({
            "id": uid, "username": username,
            "display_name": display_name or username,
            "is_private": False
        }).execute()
        return jsonify({"status": "success", "user": {"id": uid, "email": email}}), 201
    except Exception as e:
        if "already" in str(e).lower():
            return jsonify({"error": "الإيميل مستعمل"}), 400
        return jsonify({"error": str(e)}), 500


@app.route('/api/auth/login', methods=['POST'])
def login():
    d = request.get_json()
    email = d.get('email', '').strip()
    password = d.get('password', '')
    try:
        r = supabase.auth.sign_in_with_password({"email": email, "password": password})
        if not r.user:
            return jsonify({"error": "بيانات غالطة"}), 401
        p = supabase.table('profiles').select('*').eq('id', r.user.id).execute()
        return jsonify({
            "status": "success",
            "user": {"id": r.user.id, "email": r.user.email},
            "profile": p.data[0] if p.data else None
        })
    except Exception as e:
        return jsonify({"error": "إيميل أو كلمة مرور غالطين"}), 401


# ========== USERS ==========
@app.route('/api/users')
def get_users():
    if not supabase:
        return jsonify({"error": "no supabase"}), 500
    me = request.args.get('me', '')
    try:
        if me:
            r = supabase.table('profiles').select('*').neq('id', me).limit(100).execute()
        else:
            r = supabase.table('profiles').select('*').limit(100).execute()
        return jsonify({"users": r.data, "count": len(r.data)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/users/search')
def search_users():
    q = request.args.get('q', '').strip()
    me = request.args.get('me', '')
    if not q:
        return jsonify({"users": []})
    try:
        r = supabase.table('profiles').select('*').or_(
            "username.ilike.%" + q + "%,display_name.ilike.%" + q + "%"
        ).limit(30).execute()
        users = [u for u in r.data if u['id'] != me]
        return jsonify({"users": users})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/profile/<user_id>')
def get_profile(user_id):
    try:
        r = supabase.table('profiles').select('*').eq('id', user_id).execute()
        if not r.data:
            return jsonify({"error": "not found"}), 404
        return jsonify({"profile": r.data[0]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/profile/update', methods=['POST'])
def update_profile():
    d = request.get_json()
    uid = d.get('user_id')
    if not uid:
        return jsonify({"error": "user_id required"}), 400
    upd = {}
    if d.get('display_name'): upd['display_name'] = d['display_name'].strip()
    if d.get('bio') is not None: upd['bio'] = d['bio'].strip()
    if 'is_private' in d: upd['is_private'] = bool(d['is_private'])
    try:
        r = supabase.table('profiles').update(upd).eq('id', uid).execute()
        return jsonify({"status": "success", "profile": r.data[0] if r.data else None})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ========== CHATS ==========
@app.route('/api/chats/create', methods=['POST'])
def create_chat():
    d = request.get_json()
    u1, u2 = d.get('user1'), d.get('user2')
    if not u1 or not u2:
        return jsonify({"error": "missing"}), 400
    try:
        existing = supabase.table('chats').select('*').eq('is_group', False).execute()
        for c in existing.data:
            m = supabase.table('chat_members').select('user_id').eq('chat_id', c['id']).execute()
            ids = [x['user_id'] for x in m.data]
            if set(ids) == {u1, u2}:
                return jsonify({"status": "existing", "chat_id": c['id']})
        chat = supabase.table('chats').insert({"is_group": False, "created_by": u1}).execute()
        cid = chat.data[0]['id']
        supabase.table('chat_members').insert([
            {"chat_id": cid, "user_id": u1},
            {"chat_id": cid, "user_id": u2}
        ]).execute()
        return jsonify({"status": "created", "chat_id": cid}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ========== MESSAGES ==========
@app.route('/api/messages/<chat_id>')
def get_messages(chat_id):
    try:
        r = supabase.table('messages').select('*').eq('chat_id', chat_id).order('created_at').execute()
        return jsonify({"messages": r.data})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/messages/send', methods=['POST'])
def send_message():
    d = request.get_json()
    cid, sid, content = d.get('chat_id'), d.get('sender_id'), d.get('content', '').strip()
    if not cid or not sid or not content:
        return jsonify({"error": "missing"}), 400
    try:
        r = supabase.table('messages').insert({
            "chat_id": cid, "sender_id": sid,
            "content": content, "message_type": "text"
        }).execute()
        return jsonify({"message": r.data[0]}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/messages/<msg_id>', methods=['DELETE'])
def delete_message(msg_id):
    try:
        supabase.table('messages').delete().eq('id', msg_id).execute()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ========== TYPING INDICATOR ==========
@app.route('/api/typing', methods=['POST'])
def set_typing():
    d = request.get_json()
    cid, uid = d.get('chat_id'), d.get('user_id')
    try:
        supabase.table('chat_members').update({
            "typing_until": "now()"
        }).eq('chat_id', cid).eq('user_id', uid).execute()
        return jsonify({"status": "ok"})
    except:
        return jsonify({"status": "ok"})


# ========== CHAT NOTES ==========
@app.route('/api/chat/<chat_id>/note')
def get_chat_note(chat_id):
    try:
        r = supabase.table('chat_notes').select('*').eq('chat_id', chat_id).execute()
        return jsonify({"note": r.data[0] if r.data else None})
    except:
        return jsonify({"note": None})


@app.route('/api/chat/<chat_id>/note', methods=['POST'])
def save_chat_note(chat_id):
    d = request.get_json()
    uid = d.get('user_id')
    content = d.get('content', '').strip()
    if not uid or not content:
        return jsonify({"error": "missing"}), 400
    try:
        existing = supabase.table('chat_notes').select('*').eq('chat_id', chat_id).execute()
        if existing.data:
            r = supabase.table('chat_notes').update({
                "content": content, "user_id": uid
            }).eq('chat_id', chat_id).execute()
        else:
            r = supabase.table('chat_notes').insert({
                "chat_id": chat_id, "user_id": uid, "content": content
            }).execute()
        return jsonify({"note": r.data[0]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/chat/<chat_id>/note', methods=['DELETE'])
def delete_chat_note(chat_id):
    try:
        supabase.table('chat_notes').delete().eq('chat_id', chat_id).execute()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ========== POSTS ==========
@app.route('/api/posts')
def get_posts():
    try:
        r = supabase.table('posts').select('*').order('created_at', desc=True).limit(50).execute()
        posts = r.data
        # جيب أسماء المستخدمين
        for p in posts:
            try:
                prof = supabase.table('profiles').select('username, display_name').eq('id', p['user_id']).execute()
                if prof.data:
                    p['username'] = prof.data[0]['username']
                    p['display_name'] = prof.data[0]['display_name']
            except: pass
        return jsonify({"posts": posts})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/posts/create', methods=['POST'])
def create_post():
    d = request.get_json()
    uid = d.get('user_id')
    content = d.get('content', '').strip()
    image = d.get('image_url')
    if not uid or not content:
        return jsonify({"error": "المحتوى مطلوب"}), 400
    try:
        r = supabase.table('posts').insert({
            "user_id": uid, "content": content, "image_url": image
        }).execute()
        return jsonify({"post": r.data[0]}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/posts/<post_id>', methods=['DELETE'])
def delete_post(post_id):
    try:
        supabase.table('posts').delete().eq('id', post_id).execute()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
