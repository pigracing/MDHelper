import os
import re
import uuid
import requests
import mimetypes
import functools
import time
from datetime import datetime
from urllib.parse import urlparse
from flask import Flask, request, render_template_string, session, redirect, url_for, jsonify, send_file
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

app = Flask(__name__)

# ================= 配置区域 =================
app.secret_key = os.getenv('FLASK_SECRET_KEY', os.urandom(24))
APP_TOKEN = os.getenv('APP_TOKEN', 'admin123')
STORAGE_MODE = os.getenv('STORAGE_MODE', 'cloud').lower()

# 图床配置
UPLOAD_API_URL = os.getenv('UPLOAD_API_URL', "https://your.domain/upload")
AUTH_CODE = os.getenv('AUTH_CODE', "your_authCode")

# 本地配置
SITE_DOMAIN = os.getenv('SITE_DOMAIN', 'http://127.0.0.1:5000').rstrip('/')
LOCAL_IMAGE_FOLDER = 'static/uploads'
TEMP_MD_FOLDER = 'static/temp_md' # 处理后的MD文件存放处

# 确保目录存在
os.makedirs(LOCAL_IMAGE_FOLDER, exist_ok=True)
os.makedirs(TEMP_MD_FOLDER, exist_ok=True)

HEADERS = {'User-Agent': 'Apifox/1.0.0 (https://apifox.com)'}

# ================= 文件系统管理逻辑 =================

def get_file_list_from_disk():
    files_data = []
    if not os.path.exists(TEMP_MD_FOLDER):
        return []

    for filename in os.listdir(TEMP_MD_FOLDER):
        if not filename.endswith('.md'): continue
        filepath = os.path.join(TEMP_MD_FOLDER, filename)
        
        try:
            mtime = os.path.getmtime(filepath)
            dt_obj = datetime.fromtimestamp(mtime)
            time_str = dt_obj.strftime('%Y-%m-%d %H:%M:%S')
        except:
            mtime = 0
            time_str = "Unknown"

        display_name = filename
        
        # 添加时间戳参数防止浏览器缓存
        url = f"{SITE_DOMAIN}/api/download/{filename}?t={int(mtime)}"

        files_data.append({
            'filename': display_name,      
            'real_filename': filename,     
            'timestamp': time_str,
            'timestamp_sort': mtime,
            'url': url
        })

    files_data.sort(key=lambda x: x['timestamp_sort'], reverse=True)
    return files_data

# ================= 业务逻辑 =================

def auth_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        token_query = request.args.get('token')
        api_token = None
        if auth_header and auth_header.startswith("Bearer "):
            api_token = auth_header.split(" ")[1]
        elif token_query: api_token = token_query
            
        if api_token == APP_TOKEN: return f(*args, **kwargs)
        if session.get('is_logged_in'): return f(*args, **kwargs)
        if request.path.startswith('/api/'): return jsonify({"error": "Unauthorized"}), 401
        return redirect(url_for('login'))
    return decorated_function

def get_extension(url, content_type=None):
    path = urlparse(url).path
    ext = os.path.splitext(path)[1]
    if ext: return ext
    if content_type:
        ext = mimetypes.guess_extension(content_type)
        if ext: return ext
    return '.jpg'

def download_image(url):
    try:
        resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        if resp.status_code == 200:
            return resp.content, resp.headers.get('Content-Type')
        return None, None
    except: return None, None

def upload_to_cloud(image_data, filename, folder_name):
    try:
        params = {'authCode': AUTH_CODE, 'uploadFolder': folder_name}
        files = {'file': (filename, image_data, 'application/octet-stream')}
        resp = requests.post(UPLOAD_API_URL, params=params, headers=HEADERS, files=files, timeout=30)
        resp.raise_for_status()
        res = resp.json()
        if 'url' in res: return res['url']
        if 'data' in res:
            if isinstance(res['data'], dict) and 'url' in res['data']: return res['data']['url']
            return res['data']
        return None
    except Exception as e:
        print(f"Cloud Upload Error: {e}")
        return None

def save_to_local(image_data, original_url, content_type, folder_name):
    try:
        safe_folder = folder_name.replace('..', '').strip('/')
        save_dir = os.path.join(LOCAL_IMAGE_FOLDER, safe_folder)
        os.makedirs(save_dir, exist_ok=True)
        ext = get_extension(original_url, content_type)
        unique_name = f"{uuid.uuid4().hex}{ext}"
        path = os.path.join(save_dir, unique_name)
        with open(path, 'wb') as f: f.write(image_data)
        return f"{SITE_DOMAIN}/{LOCAL_IMAGE_FOLDER}/{safe_folder}/{unique_name}"
    except: return None

def process_markdown_content(content, filename_no_ext):
    pattern = re.compile(r'!\[(.*?)\]\((.*?)\)')
    def replace_callback(match):
        alt, url = match.group(1), match.group(2)
        if not url.startswith(('http://', 'https://')): return match.group(0)
        if STORAGE_MODE == 'local' and SITE_DOMAIN in url: return match.group(0)

        img_data, c_type = download_image(url)
        if not img_data: return match.group(0)

        fname = url.split('/')[-1].split('?')[0] or "image.jpg"
        new_url = None
        if STORAGE_MODE == 'cloud':
            new_url = upload_to_cloud(img_data, fname, filename_no_ext)
        else:
            new_url = save_to_local(img_data, url, c_type, filename_no_ext)
        return f'![{alt}]({new_url})' if new_url else match.group(0)
    return pattern.sub(replace_callback, content)

def save_processed_md(content, original_filename):
    safe_filename = os.path.basename(original_filename)
    save_path = os.path.join(TEMP_MD_FOLDER, safe_filename)
    with open(save_path, 'w', encoding='utf-8') as f:
        f.write(content)
    return f"{SITE_DOMAIN}/api/download/{safe_filename}"

# ================= HTML 模板 =================

BASE_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>Markdown 资源迁移器</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body { background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); min-height: 100vh; color: #e2e8f0; }
        .glass { background: rgba(255, 255, 255, 0.05); backdrop-filter: blur(16px); border: 1px solid rgba(255, 255, 255, 0.1); box-shadow: 0 4px 30px rgba(0, 0, 0, 0.1); }
        .btn-disabled { background-color: #475569 !important; color: #94a3b8 !important; cursor: not-allowed !important; }
        .search-input:focus { outline: none; border-color: #60a5fa; box-shadow: 0 0 0 2px rgba(96, 165, 250, 0.3); }
        /* 自定义滚动条样式 */
        .scroll-custom::-webkit-scrollbar { width: 6px; }
        .scroll-custom::-webkit-scrollbar-track { background: transparent; }
        .scroll-custom::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.2); border-radius: 3px; }
    </style>
</head>
<body class="flex flex-col items-center justify-start p-4 md:p-10">
    {{ content_html|safe }}
</body>
</html>
"""

LOGIN_CONTENT = """
<div class="glass rounded-2xl p-8 w-full max-w-md mt-20">
    <h2 class="text-3xl font-bold mb-6 text-center text-white">系统登录</h2>
    <form method="post">
        <div class="mb-6"><input type="password" name="token" class="w-full px-4 py-3 rounded-xl bg-white/5 border border-white/10 text-white" placeholder="Token" required></div>
        {% if error %}<div class="text-red-400 text-center mb-4">{{ error }}</div>{% endif %}
        <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 rounded-xl">进入系统</button>
    </form>
</div>
"""

INDEX_CONTENT = """
<div class="w-full max-w-4xl space-y-6">
    <!-- Header -->
    <div class="flex justify-between items-center mb-4">
        <h1 class="text-2xl font-bold text-white">MD 图片迁移 <span class="text-xs text-blue-400 border border-blue-400/30 px-2 py-0.5 rounded ml-2">{{ mode|upper }}</span></h1>
        <a href="/logout" class="text-xs bg-white/5 hover:bg-white/10 px-4 py-2 rounded-lg transition border border-white/10">退出</a>
    </div>

    <!-- Upload Area -->
    <div class="glass rounded-2xl p-8">
        <form method="post" enctype="multipart/form-data" id="uploadForm">
            <div class="border-2 border-dashed border-gray-600 rounded-xl p-10 text-center hover:bg-white/5 transition cursor-pointer relative group" id="dropZone">
                <input type="file" name="file" accept=".md" class="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-50" required onchange="updateFileName(this)">
                <div id="fileLabel" class="pointer-events-none group-hover:scale-105 transition duration-300">
                    <svg class="w-12 h-12 mx-auto mb-3 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"></path></svg>
                    <p class="text-lg font-medium text-gray-200">点击或拖拽 Markdown 文件</p>
                </div>
                <div id="fileName" class="hidden text-xl font-bold text-blue-300 pointer-events-none break-all"></div>
            </div>
            <button type="submit" id="submitBtn" disabled class="w-full btn-disabled font-bold py-4 rounded-xl mt-6 transition shadow-lg text-white bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-500 hover:to-purple-500" onclick="this.innerText='正在处理...';this.classList.add('opacity-75', 'cursor-wait')">请先选择文件</button>
        </form>
    </div>

    <!-- History Area -->
    <div class="glass rounded-2xl p-6">
        <div class="flex flex-col md:flex-row justify-between items-center mb-6 gap-4">
            <h2 class="text-xl font-bold flex items-center gap-2">
                <svg class="w-5 h-5 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                历史文件列表
            </h2>
            <div class="relative w-full md:w-64">
                <div class="absolute inset-y-0 left-0 flex items-center pl-3 pointer-events-none">
                    <svg class="w-4 h-4 text-gray-400" fill="none" viewBox="0 0 20 20"><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="m19 19-4-4m0-7A7 7 0 1 1 1 8a7 7 0 0 1 14 0Z"/></svg>
                </div>
                <input type="text" id="searchInput" onkeyup="filterTable()" class="search-input block w-full p-2 pl-10 text-sm text-white border border-gray-600 rounded-lg bg-white/5 placeholder-gray-400 focus:bg-white/10 transition" placeholder="搜索文件名...">
            </div>
        </div>

        {% if history %}
        <!-- 
            核心修改：
            max-h-[320px]: 限制最大高度 (约 5-6 行)
            overflow-y-auto: 超出高度显示滚动条
            scroll-custom: 自定义滚动条样式
        -->
        <div class="overflow-x-auto overflow-y-auto max-h-[320px] rounded-lg border border-gray-700 scroll-custom relative">
            <table class="w-full text-left text-sm text-gray-300" id="historyTable">
                <!-- 
                   sticky top-0: 表头固定
                   bg-slate-900: 给表头加背景色，防止滚动时内容重叠
                   z-10: 确保表头在内容之上
                -->
                <thead class="sticky top-0 z-10 bg-slate-900 text-xs uppercase text-gray-400 shadow-md">
                    <tr><th class="px-4 py-3">文件名</th><th class="px-4 py-3">处理时间</th><th class="px-4 py-3 text-right">操作</th></tr>
                </thead>
                <tbody class="divide-y divide-gray-700/50">
                    {% for item in history %}
                    <tr class="hover:bg-white/5 transition duration-150">
                        <td class="px-4 py-3 font-medium text-white break-all file-name-cell">{{ item.filename }}</td>
                        <td class="px-4 py-3 whitespace-nowrap text-gray-400">{{ item.timestamp }}</td>
                        <td class="px-4 py-3 text-right whitespace-nowrap">
                            <a href="{{ item.url }}" target="_blank" class="inline-flex items-center px-3 py-1.5 bg-blue-500/20 hover:bg-blue-500/40 text-blue-300 rounded-md text-xs font-bold transition">
                                <svg class="w-3 h-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
                                下载
                            </a>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            <div id="noResult" class="hidden text-center py-4 text-gray-500 text-sm">未找到匹配的文件</div>
        </div>
        {% else %}
        <div class="text-center py-8 text-gray-500 text-sm border-2 border-dashed border-gray-700 rounded-xl">暂无记录</div>
        {% endif %}
    </div>
</div>

<script>
    function updateFileName(input) {
        const btn = document.getElementById('submitBtn');
        if(input.files && input.files[0]) {
            document.getElementById('fileLabel').classList.add('hidden');
            const fn = document.getElementById('fileName'); fn.innerText = input.files[0].name; fn.classList.remove('hidden');
            btn.disabled = false; btn.innerText = "开始处理"; btn.classList.remove('btn-disabled');
        }
    }

    function filterTable() {
        const input = document.getElementById('searchInput');
        const filter = input.value.toLowerCase();
        const table = document.getElementById('historyTable');
        const tr = table.getElementsByTagName('tr');
        const noResult = document.getElementById('noResult');
        let hasVisibleRow = false;

        for (let i = 1; i < tr.length; i++) {
            const td = tr[i].getElementsByClassName('file-name-cell')[0];
            if (td) {
                const txtValue = td.textContent || td.innerText;
                if (txtValue.toLowerCase().indexOf(filter) > -1) {
                    tr[i].style.display = "";
                    hasVisibleRow = true;
                } else {
                    tr[i].style.display = "none";
                }
            }
        }
        
        if (!hasVisibleRow && tr.length > 1) {
            noResult.classList.remove('hidden');
        } else {
            noResult.classList.add('hidden');
        }
    }
</script>
"""

SUCCESS_CONTENT = """
<div class="glass rounded-2xl p-10 w-full max-w-lg text-center mt-10">
    <div class="mb-6 inline-flex p-4 rounded-full bg-green-500/20 shadow-[0_0_20px_rgba(34,197,94,0.3)]">
        <svg class="w-10 h-10 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>
    </div>
    <h2 class="text-3xl font-bold mb-2 text-white">处理成功!</h2>
    <p class="text-gray-400 mb-8">文件已保存。</p>
    <div class="space-y-4">
        <a href="{{ download_url }}" target="_blank" class="block w-full bg-white text-gray-900 font-bold py-3 rounded-xl transition hover:bg-gray-200 shadow-lg flex items-center justify-center gap-2">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
            立即下载
        </a>
        <a href="/" class="block w-full text-gray-400 hover:text-white py-2 transition">返回列表</a>
    </div>
</div>
"""

# ================= 路由定义 =================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('token') == APP_TOKEN:
            session['is_logged_in'] = True
            return redirect(url_for('index'))
        else: return render_template_string(BASE_TEMPLATE, content_html=render_template_string(LOGIN_CONTENT, error="无效的 Token"))
    return render_template_string(BASE_TEMPLATE, content_html=render_template_string(LOGIN_CONTENT, error=None))

@app.route('/logout')
def logout():
    session.pop('is_logged_in', None)
    return redirect(url_for('login'))

@app.route('/', methods=['GET', 'POST'])
@auth_required
def index():
    if request.method == 'POST':
        if 'file' not in request.files: return "无文件", 400
        file = request.files['file']
        if not file.filename: return "未选择文件", 400
        try:
            md_name = os.path.splitext(file.filename)[0]
            content = file.read().decode('utf-8', errors='ignore')
            new_content = process_markdown_content(content, md_name)
            download_url = save_processed_md(new_content, file.filename)
            return render_template_string(BASE_TEMPLATE, content_html=render_template_string(SUCCESS_CONTENT, download_url=download_url))
        except Exception as e: return f"Error: {e}", 500

    history = get_file_list_from_disk()
    inner_html = render_template_string(INDEX_CONTENT, mode=STORAGE_MODE, history=history)
    return render_template_string(BASE_TEMPLATE, content_html=inner_html)

@app.route('/api/process', methods=['POST'])
@auth_required
def api_process():
    if 'file' not in request.files: return jsonify({"code": 400, "error": "No file uploaded"}), 400
    file = request.files['file']
    if not file.filename: return jsonify({"code": 400, "error": "Empty filename"}), 400
    try:
        md_name = os.path.splitext(file.filename)[0]
        content = file.read().decode('utf-8', errors='ignore')
        new_content = process_markdown_content(content, md_name)
        download_url = save_processed_md(new_content, file.filename)
        return jsonify({"code": 200, "message": "success", "filename": file.filename, "url": download_url})
    except Exception as e: return jsonify({"code": 500, "error": str(e)}), 500

@app.route('/api/history', methods=['GET'])
@auth_required
def api_history():
    try:
        files = get_file_list_from_disk()
        return jsonify({"code": 200, "message": "success", "data": files})
    except Exception as e: return jsonify({"code": 500, "error": str(e)}), 500

@app.route('/api/download/<filename>', methods=['GET'])
@auth_required
def api_download(filename):
    safe_filename = os.path.basename(filename)
    file_path = os.path.join(TEMP_MD_FOLDER, safe_filename)
    if not os.path.exists(file_path): return jsonify({"code": 404, "error": "File not found"}), 404
    try:
        return send_file(file_path, as_attachment=True, download_name=safe_filename, mimetype='text/markdown')
    except Exception as e: return jsonify({"code": 500, "error": str(e)}), 500

if __name__ == '__main__':
    # 获取环境变量 PORT，默认为 7860
    port = int(os.environ.get('PORT', 7860))
    # host='0.0.0.0' 允许外部访问
    app.run(debug=True, host='0.0.0.0', port=port)