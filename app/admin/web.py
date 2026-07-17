import math, os, threading, asyncio
from flask import Flask, render_template_string, request, redirect, url_for, flash, jsonify
from app.config import FLASK_SECRET, BOT_TOKEN
from app import database
from aiogram import Bot

app = Flask(__name__)
app.secret_key = FLASK_SECRET

BCAST_PER_PAGE = 4
FILTERS_PER_PAGE = 10

def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

# Initialize DB and Redis on startup
run_async(database.init_db())

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
    font-family: 'Inter', sans-serif;
    background: #000;
    min-height: 100vh;
    color: #fff;
    overflow-x: hidden;
}

/* Animated background */
body::before {
    content: '';
    position: fixed;
    inset: 0;
    background: radial-gradient(ellipse at 20% 20%, rgba(255,255,255,0.04) 0%, transparent 60%),
                radial-gradient(ellipse at 80% 80%, rgba(255,255,255,0.03) 0%, transparent 60%);
    pointer-events: none;
    z-index: 0;
}

.container { max-width: 900px; margin: 0 auto; padding: 40px 20px; position: relative; z-index: 1; }

/* Glowing title */
.site-title {
    text-align: center;
    margin-bottom: 48px;
}
.site-title h1 {
    font-size: 2.6rem;
    font-weight: 700;
    letter-spacing: 0.02em;
    color: transparent;
    background: linear-gradient(135deg, #ffffff 0%, #999 50%, #ffffff 100%);
    background-size: 200% 200%;
    -webkit-background-clip: text;
    background-clip: text;
    animation: shimmer 4s ease-in-out infinite;
    filter: drop-shadow(0 0 30px rgba(255,255,255,0.4)) drop-shadow(0 0 60px rgba(255,255,255,0.15));
    text-shadow: none;
    position: relative;
}
.site-title h1::after {
    content: attr(data-text);
    position: absolute;
    inset: 0;
    background: linear-gradient(135deg, transparent 30%, rgba(255,255,255,0.6) 50%, transparent 70%);
    background-size: 300% 100%;
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
    animation: sweep 3s ease-in-out infinite;
}
@keyframes shimmer {
    0%, 100% { background-position: 0% 50%; }
    50% { background-position: 100% 50%; }
}
@keyframes sweep {
    0% { background-position: -100% 0; }
    100% { background-position: 200% 0; }
}

/* Glass card */
.card {
    background: rgba(255,255,255,0.04);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 20px;
    padding: 28px;
    margin-bottom: 24px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.08);
    transition: transform 0.2s ease, box-shadow 0.2s ease;
    animation: floatIn 0.4s ease forwards;
}
.card:hover {
    transform: translateY(-2px);
    box-shadow: 0 16px 40px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.1);
}
@keyframes floatIn {
    from { opacity: 0; transform: translateY(16px); }
    to { opacity: 1; transform: translateY(0); }
}

.card-title {
    font-size: 1.1rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: rgba(255,255,255,0.55);
    margin-bottom: 20px;
    padding-bottom: 12px;
    border-bottom: 1px solid rgba(255,255,255,0.08);
}

/* Form elements */
.form-row { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 8px; }
input[type="text"], textarea {
    flex: 1;
    min-width: 160px;
    padding: 10px 14px;
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 10px;
    color: #fff;
    font-family: inherit;
    font-size: 0.875rem;
    outline: none;
    transition: border-color 0.2s, background 0.2s;
}
input[type="text"]:focus, textarea:focus {
    border-color: rgba(255,255,255,0.3);
    background: rgba(255,255,255,0.09);
}
input::placeholder, textarea::placeholder { color: rgba(255,255,255,0.3); }

/* Buttons */
.btn {
    padding: 10px 18px;
    border: none;
    border-radius: 10px;
    font-family: inherit;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    white-space: nowrap;
}
.btn-primary {
    background: rgba(255,255,255,0.12);
    color: #fff;
    border: 1px solid rgba(255,255,255,0.2);
}
.btn-primary:hover { background: rgba(255,255,255,0.2); transform: translateY(-1px); }
.btn-danger {
    background: rgba(255,60,60,0.15);
    color: #ff6b6b;
    border: 1px solid rgba(255,60,60,0.25);
}
.btn-danger:hover { background: rgba(255,60,60,0.25); transform: translateY(-1px); }
.btn-sm { padding: 6px 12px; font-size: 0.8rem; border-radius: 8px; }

/* Table */
table { width: 100%; border-collapse: collapse; margin-top: 12px; }
th {
    text-align: left;
    padding: 10px 12px;
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: rgba(255,255,255,0.35);
    border-bottom: 1px solid rgba(255,255,255,0.07);
}
td {
    padding: 12px 12px;
    font-size: 0.875rem;
    color: rgba(255,255,255,0.8);
    border-bottom: 1px solid rgba(255,255,255,0.05);
    vertical-align: middle;
    max-width: 220px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
tr:last-child td { border-bottom: none; }
tr:hover td { background: rgba(255,255,255,0.02); }

.empty { text-align: center; padding: 24px; color: rgba(255,255,255,0.25); font-size: 0.875rem; }

/* Flash */
.flash-msg {
    padding: 12px 20px;
    background: rgba(255,255,255,0.08);
    border: 1px solid rgba(255,255,255,0.15);
    border-radius: 12px;
    margin-bottom: 20px;
    font-size: 0.875rem;
    color: #fff;
    animation: floatIn 0.3s ease;
}

/* Badge */
.badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 6px;
    font-size: 0.72rem;
    font-weight: 500;
    background: rgba(255,255,255,0.08);
    color: rgba(255,255,255,0.5);
    border: 1px solid rgba(255,255,255,0.1);
}

/* Pagination */
.pagination { display: flex; gap: 8px; margin-top: 16px; justify-content: center; flex-wrap: wrap; }
.page-btn {
    padding: 7px 14px;
    border-radius: 8px;
    border: 1px solid rgba(255,255,255,0.12);
    background: rgba(255,255,255,0.05);
    color: rgba(255,255,255,0.6);
    font-size: 0.8rem;
    cursor: pointer;
    text-decoration: none;
    transition: all 0.2s;
}
.page-btn:hover, .page-btn.active {
    background: rgba(255,255,255,0.15);
    color: #fff;
    border-color: rgba(255,255,255,0.25);
}

/* Link */
a { color: rgba(255,255,255,0.55); text-decoration: none; }
a:hover { color: #fff; }

/* Broadcast text truncate in table */
.bcast-preview { max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* Modal-style edit form */
.edit-form { display: none; padding: 16px; background: rgba(255,255,255,0.04); border-radius: 12px; margin-top: 12px; border: 1px solid rgba(255,255,255,0.1); }

/* Table Wrapper for horizontal scroll */
.table-wrapper {
    width: 100%;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    margin-top: 12px;
}

/* Responsive adjustments */
@media (max-width: 768px) {
    .container { padding: 20px 12px; }
    .site-title h1 { font-size: 1.8rem; }
    .card { padding: 18px; border-radius: 16px; }
    .form-row { flex-direction: column; }
    .btn { width: 100%; }
    input[type="text"], textarea { width: 100%; }
    
    .stats-strip { gap: 20px !important; }
    .stats-strip > div { flex: 1; min-width: 100px; }
    
    .bcast-preview { max-width: 120px; font-size: 0.75rem; white-space: normal; word-break: break-all; }
    .edit-form textarea { font-size: 0.8rem; padding: 8px; }

    td, th { padding: 8px 10px; font-size: 0.8rem; }
}

/* Swipe Indicator */
.swipe-hint {
  display: none;
  text-align: center;
  font-size: 0.7rem;
  color: rgba(255,255,255,0.2);
  margin-top: 8px;
  text-transform: uppercase;
  letter-spacing: 0.1em;
}
@media (max-width: 768px) { .swipe-hint { display: block; } }

/* Leaderboard specific */
.leaderboard-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: rgba(255,255,255,0.03);
  border-radius: 12px;
  margin-bottom: 8px;
  border: 1px solid rgba(255,255,255,0.05);
}
.rank { font-weight: 700; color: rgba(255,255,255,0.3); width: 24px; }
.user-info { flex: 1; margin-left: 12px; }
.user-id { font-family: monospace; font-size: 0.85rem; color: #fff; }
.stats-mini { font-size: 0.72rem; color: rgba(255,255,255,0.4); margin-top: 2px; }
.score { font-weight: 700; font-size: 1.1rem; color: #fff; }
"""

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AnimexPlayBot Admin</title>
<style>{{ css }}</style>
</head>
<body>
<div class="container">

  <div class="site-title">
    <h1 data-text="AnimexPlayBot Admin">AnimexPlayBot Admin</h1>
  </div>

  {% with messages = get_flashed_messages() %}
    {% if messages %}
      {% for msg in messages %}
        <div class="flash-msg">{{ msg }}</div>
      {% endfor %}
    {% endif %}
  {% endwith %}

  <!-- Stats Strip -->
  <div class="card" style="padding: 18px 28px;">
    <div class="stats-strip" style="display:flex; gap:40px; align-items:center; flex-wrap:wrap;">
      <div><div style="font-size:1.8rem;font-weight:700;">{{ total_users }}</div><div style="font-size:0.75rem;color:rgba(255,255,255,0.35);margin-top:2px;letter-spacing:.05em;text-transform:uppercase;">Total Users</div></div>
      <div><div style="font-size:1.8rem;font-weight:700;">{{ total_filters }}</div><div style="font-size:0.75rem;color:rgba(255,255,255,0.35);margin-top:2px;letter-spacing:.05em;text-transform:uppercase;">Filters</div></div>
      <div><div style="font-size:1.8rem;font-weight:700;">{{ total_broadcasts }}</div><div style="font-size:0.75rem;color:rgba(255,255,255,0.35);margin-top:2px;letter-spacing:.05em;text-transform:uppercase;">Broadcasts</div></div>
      <div><div style="font-size:1.8rem;font-weight:700;">{{ total_indexed }}</div><div style="font-size:0.75rem;color:rgba(255,255,255,0.35);margin-top:2px;letter-spacing:.05em;text-transform:uppercase;">Indexed Files</div></div>
    </div>
  </div>

  <!-- Filters -->
  <div class="card" id="filters-card">
    <div class="card-title">Filters</div>
    <form action="{{ url_for('add_filter_route') }}" method="POST">
      <div class="form-row">
        <input type="text" name="keyword" placeholder="Keyword (e.g. One Piece)" required>
        <input type="text" name="reply_text" placeholder="[Button Text](buttonurl:link)" required>
        <input type="text" name="file_id" placeholder="Optional Sticker ID">
        <button type="submit" class="btn btn-primary">Add Filter</button>
      </div>
    </form>
    {% if filters %}
    <div class="table-wrapper">
    <table>
      <tr><th>Keyword</th><th>Reply Data</th><th>Sticker ID</th><th></th></tr>
      {% for f in filters %}
      <tr>
        <td><span class="badge">{{ f.keyword }}</span></td>
        <td title="{{ f.reply_text }}">{{ f.reply_text[:50] }}{% if f.reply_text|length > 50 %}…{% endif %}</td>
        <td style="font-size:0.72rem;color:rgba(255,255,255,0.3);">{{ f.file_id[:20] + '…' if f.file_id and f.file_id|length > 20 else (f.file_id or '—') }}</td>
        <td>
          <form action="{{ url_for('delete_filter_route', keyword=f.keyword) }}" method="POST" style="display:inline;">
            <button class="btn btn-danger btn-sm">Delete</button>
          </form>
        </td>
      </tr>
      {% endfor %}
    </table>
    </div>
    <!-- Filter Pagination -->
    {% if filters_total_pages > 1 %}
    <div class="pagination">
      {# Show First + Ellipsis #}
      {% if filters_page > 2 %}
        <a href="{{ url_for('index', fpage=0, bpage=bcast_page) }}" class="page-btn">1</a>
        {% if filters_page > 3 %}<span style="align-self:center; opacity:0.3;">...</span>{% endif %}
      {% endif %}

      {# Current Range #}
      {% for p in range(0, filters_total_pages) %}
        {% if p >= filters_page - 2 and p <= filters_page + 2 %}
          <a href="{{ url_for('index', fpage=p, bpage=bcast_page) }}" class="page-btn {% if p == filters_page %}active{% endif %}">{{ p + 1 }}</a>
        {% endif %}
      {% endfor %}

      {# Ellipsis + Last #}
      {% if filters_page < filters_total_pages - 3 %}
        {% if filters_page < filters_total_pages - 4 %}<span style="align-self:center; opacity:0.3;">...</span>{% endif %}
        <a href="{{ url_for('index', fpage=filters_total_pages-1, bpage=bcast_page) }}" class="page-btn">{{ filters_total_pages }}</a>
      {% endif %}
    </div>
    <div class="swipe-hint">Swipe left/right to change page</div>
    {% endif %}
    {% else %}<div class="empty">No filters yet.</div>{% endif %}
  </div>

  <!-- Broadcast History -->
  <div class="card">
    <div class="card-title">Broadcast History</div>
    {% if broadcasts %}
    <div class="table-wrapper">
    <table>
      <tr><th>ID</th><th>Preview</th><th>Sent At</th><th></th></tr>
      {% for b in broadcasts %}
      <tr>
        <td style="color:rgba(255,255,255,0.35);font-size:0.8rem;">#{{ b.id }}</td>
        <td class="bcast-preview" title="{{ b.text }}">{{ b.text[:60] }}{% if b.text|length > 60 %}…{% endif %}</td>
        <td style="color:rgba(255,255,255,0.35);font-size:0.8rem;">{{ b.sent_at }}</td>
        <td style="white-space:nowrap;">
          <button class="btn btn-primary btn-sm" onclick="toggleEdit({{ b.id }})">Edit</button>
          <form action="{{ url_for('delete_broadcast_route', bid=b.id) }}" method="POST" style="display:inline;" onsubmit="return confirm('Delete this broadcast?')">
            <button class="btn btn-danger btn-sm">Delete</button>
          </form>
        </td>
      </tr>
      <tr>
        <td colspan="4" style="padding:0;border:none;">
          <div class="edit-form" id="edit-{{ b.id }}">
            <form action="{{ url_for('update_broadcast_route', bid=b.id) }}" method="POST">
              <textarea name="text" rows="3" style="width:100%;margin-bottom:8px;">{{ b.text }}</textarea>
              <button type="submit" class="btn btn-primary btn-sm">Save Changes</button>
            </form>
          </div>
        </td>
      </tr>
      {% endfor %}
    </table>
    </div>
    <!-- Pagination -->
    {% if total_pages > 1 %}
    <div class="pagination">
      {% for p in range(total_pages) %}
        <a href="{{ url_for('index', bpage=p, fpage=filters_page) }}" class="page-btn {% if p == bcast_page %}active{% endif %}">{{ p + 1 }}</a>
      {% endfor %}
    </div>
    {% endif %}
    {% else %}<div class="empty">No broadcasts yet.</div>{% endif %}
  </div>

  <!-- Auto-Index -->
  <div class="card">
    <div class="card-title">Auto-Indexed Files</div>
    {% if auto_index %}
    <div class="table-wrapper">
    <table>
      <tr><th>Msg ID</th><th>File Name</th><th>Caption</th><th></th></tr>
      {% for idx in auto_index %}
      <tr>
        <td style="color:rgba(255,255,255,0.35);font-size:0.8rem;">{{ idx.message_id }}</td>
        <td title="{{ idx.file_name }}">{{ (idx.file_name or '—')[:30] }}</td>
        <td style="color:rgba(255,255,255,0.45);">{{ (idx.caption or '')[:20] }}</td>
        <td><a href="{{ idx.message_url }}" target="_blank" style="color:rgba(255,255,255,0.5);font-size:0.8rem;">View ↗</a></td>
      </tr>
      {% endfor %}
    </table>
    </div>
    {% else %}<div class="empty">No files indexed yet.</div>{% endif %}
  </div>

  <!-- User Leaderboard -->
  <div class="card">
    <div class="card-title">Top Users (Leaderboard)</div>
    {% if leaderboard %}
      {% for u in leaderboard %}
      <div class="leaderboard-row">
        <div class="rank">#{{ loop.index }}</div>
        <div class="user-info">
          <div class="user-id">{{ u.user_id }}</div>
          <div class="stats-mini">{{ u.messages_count }} msgs • {{ u.filters_asked_count }} searches</div>
        </div>
        <div class="score">{{ u.messages_count + u.filters_asked_count }}</div>
      </div>
      {% endfor %}
    {% else %}
      <div class="empty">No activity data yet.</div>
    {% endif %}
  </div>

</div>
<script>
function toggleEdit(id) {
  const el = document.getElementById('edit-' + id);
  el.style.display = el.style.display === 'block' ? 'none' : 'block';
}

// Swipe / Trackpad Pagination for Filters
(function() {
    const card = document.getElementById('filters-card');
    if (!card) return;

    let touchStartX = 0;
    let touchEndX = 0;
    
    const currentPage = {{ filters_page }};
    const totalPages = {{ filters_total_pages }};
    const bPage = {{ bcast_page }};

    function navigate(dir) {
        let nextPage = currentPage + dir;
        if (nextPage >= 0 && nextPage < totalPages) {
            window.location.href = `/?fpage=${nextPage}&bpage=${bPage}`;
        }
    }

    // Touch events for mobile
    card.addEventListener('touchstart', e => {
        touchStartX = e.changedTouches[0].screenX;
    }, {passive: true});

    card.addEventListener('touchend', e => {
        touchEndX = e.changedTouches[0].screenX;
        handleSwipe();
    }, {passive: true});

    function handleSwipe() {
        if (Math.abs(touchEndX - touchStartX) > 100) {
            if (touchEndX < touchStartX) navigate(1); // Swipe left -> Next
            if (touchEndX > touchStartX) navigate(-1); // Swipe right -> Prev
        }
    }

    // Trackpad horizontal scroll
    let scrollAccumulator = 0;
    card.addEventListener('wheel', e => {
        // Only trigger if it's primary horizontal scrolling
        if (Math.abs(e.deltaX) > Math.abs(e.deltaY)) {
            scrollAccumulator += e.deltaX;
            if (Math.abs(scrollAccumulator) > 300) {
                navigate(scrollAccumulator > 0 ? 1 : -1);
                scrollAccumulator = 0;
            }
            e.preventDefault();
        } else {
            scrollAccumulator = 0;
        }
    }, {passive: false});
})();
</script>
</body>
</html>"""

@app.route('/')
def index():
    bcast_page = int(request.args.get('bpage', 0))
    filters_page = int(request.args.get('fpage', 0))
    
    async def get_data():
        total_users = await database.get_total_users()
        total_filters = len(await database.get_all_filter_keywords())
        
        # Filters
        from sqlalchemy import select, func
        async with database.AsyncSessionLocal() as session:
            count_filters = await session.execute(select(func.count(database.Filter.keyword)))
            total_filters = count_filters.scalar()
            filters_res = await session.execute(
                select(database.Filter).order_by(database.Filter.keyword.asc())
                .limit(FILTERS_PER_PAGE).offset(filters_page * FILTERS_PER_PAGE)
            )
            filters_raw = filters_res.scalars().all()
            
            # Broadcasts
            total_bcasts_res = await session.execute(select(func.count(database.Broadcast.id)))
            total_broadcasts = total_bcasts_res.scalar()
            bcasts_res = await session.execute(
                select(database.Broadcast).order_by(database.Broadcast.id.desc())
                .limit(BCAST_PER_PAGE).offset(bcast_page * BCAST_PER_PAGE)
            )
            broadcasts_raw = bcasts_res.scalars().all()
            
            # Auto Index
            total_idx_res = await session.execute(select(func.count(database.AutoIndex.message_id)))
            total_indexed = total_idx_res.scalar()
            idx_res = await session.execute(
                select(database.AutoIndex).order_by(database.AutoIndex.message_id.desc()).limit(20)
            )
            auto_index = idx_res.scalars().all()
            
            # Leaderboard
            leaderboard = await database.get_leaderboard(10)
            
        return {
            "total_users": total_users,
            "total_filters": total_filters,
            "filters": filters_raw,
            "total_broadcasts": total_broadcasts,
            "broadcasts": broadcasts_raw,
            "total_indexed": total_indexed,
            "auto_index": auto_index,
            "leaderboard": leaderboard
        }

    data = run_async(get_data())
    
    bcast_total_pages = max(1, math.ceil(data["total_broadcasts"] / BCAST_PER_PAGE))
    filters_total_pages = max(1, math.ceil(data["total_filters"] / FILTERS_PER_PAGE))
    
    return render_template_string(
        HTML.replace("{{ css }}", CSS),
        filters=data["filters"],
        broadcasts=data["broadcasts"],
        auto_index=data["auto_index"],
        total_users=data["total_users"],
        total_filters=data["total_filters"],
        total_broadcasts=data["total_broadcasts"],
        total_indexed=data["total_indexed"],
        bcast_page=bcast_page,
        total_pages=bcast_total_pages,
        filters_page=filters_page,
        filters_total_pages=filters_total_pages,
        leaderboard=data["leaderboard"]
    )

@app.route('/add_filter', methods=['POST'])
def add_filter_route():
    keyword = request.form.get('keyword', '').strip().lower()
    reply_text = request.form.get('reply_text', '').strip()
    file_id = request.form.get('file_id', '').strip() or None
    if keyword and reply_text:
        run_async(database.add_filter(keyword, reply_text, file_id))
        flash(f'Filter "{keyword}" added.')
    return redirect(url_for('index'))

@app.route('/delete_filter/<keyword>', methods=['POST'])
def delete_filter_route(keyword):
    run_async(database.delete_filter(keyword))
    flash(f'Filter "{keyword}" deleted.')
    return redirect(url_for('index'))

@app.route('/delete_index/<int:message_id>', methods=['POST'])
def delete_index_route(message_id):
    async def delete_idx():
        async with database.AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(database.delete(database.AutoIndex).where(database.AutoIndex.message_id == message_id))
    run_async(delete_idx())
    flash(f'Index entry {message_id} deleted.')
    return redirect(url_for('index'))

@app.route('/delete_broadcast/<int:bid>', methods=['POST'])
def delete_broadcast_route(bid):
    run_async(database.delete_broadcast(bid))
    flash(f'Broadcast #{bid} deleted.')
    return redirect(url_for('index'))

def run_telegram_edit(bid, text):
    async def edit_task():
        bot_instance = Bot(token=BOT_TOKEN)
        sent_messages = await database.get_sent_broadcast_messages(bid)
        for uid, mid in sent_messages:
            try:
                await bot_instance.edit_message_text(chat_id=uid, message_id=mid, text=text)
                await asyncio.sleep(0.05)
            except:
                try:
                    await bot_instance.edit_message_caption(chat_id=uid, message_id=mid, caption=text)
                    await asyncio.sleep(0.05)
                except:
                    pass
        await bot_instance.session.close()

    new_loop = asyncio.new_event_loop()
    new_loop.run_until_complete(edit_task())
    new_loop.close()

@app.route('/update_broadcast/<int:bid>', methods=['POST'])
def update_broadcast_route(bid):
    text = request.form.get('text', '').strip()
    if text:
        run_async(database.update_broadcast(bid, text))
        
        # Start background thread to update Telegram messages
        thread = threading.Thread(target=run_telegram_edit, args=(bid, text))
        thread.daemon = True
        thread.start()
        
        flash(f'Broadcast #{bid} updated. Editing Telegram messages in background...')
    return redirect(url_for('index'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    print(f"Admin Dashboard → http://localhost:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)
