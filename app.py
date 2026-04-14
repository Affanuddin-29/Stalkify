from flask import Flask, render_template, request, redirect, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import datetime
import yfinance as yf
import os
from collections import Counter
from flask_login import login_user
from werkzeug.utils import secure_filename

app = Flask(__name__)

UPLOAD_FOLDER = "static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

app.config['SECRET_KEY'] = 'secret123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# ---------------- MODELS ----------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100))
    password = db.Column(db.String(100))

profile_pic = db.Column(db.String(200), default="default.png")

class Watchlist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    stock = db.Column(db.String(10))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

class History(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    stock = db.Column(db.String(10))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    suggestion = db.Column(db.String(10))  # BUY / SELL
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# CREATE DB
with app.app_context():
    db.create_all()

# ---------------- HOME ----------------
@app.route("/")
def home():
    import requests

    API_KEY = "5ff6e7164b134c859d31e7707e2cbeaa"

    url = f"https://newsapi.org/v2/top-headlines?category=business&language=en&pageSize=5&apiKey={API_KEY}"

    res = requests.get(url)
    data = res.json()

    news_data = []

    for article in data.get("articles", []):
        image = article.get("urlToImage")

        # 🔥 FIX: fallback image if None
        if not image:
            image = "https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3"

        news_data.append({
            "title": article.get("title"),
            "source": article.get("source", {}).get("name"),
            "url": article.get("url"),
            "image": image
        })

    return render_template("index.html", news=news_data)

# ---------------- ANALYZE ----------------
@app.route("/analyze/<symbol>")
def analyze(symbol):
    symbol = symbol.upper().strip()

    try:
        # Fetch stock data
        ticker = yf.Ticker(symbol)
        data = ticker.history(period="30d")

        if data.empty:
            return "Stock not found"

        # Prices
        prices = data["Close"].tolist()
        price = round(prices[-1], 2)

        # Percentage change
        open_price = data["Open"].iloc[0]
        percent = round(((price - open_price) / open_price) * 100, 2)

        # Signal
        signal = "BUY" if percent > 0 else "SELL"
        color = "green" if percent > 0 else "red"

        # ✅ SAVE HISTORY (VERY IMPORTANT)
        if current_user.is_authenticated:
            new = History(
                user_id=current_user.id,
                stock=symbol,
                suggestion=signal,
                timestamp=datetime.utcnow()
            )
            db.session.add(new)
            db.session.commit()

        # Render page
        return render_template(
            "analyze.html",
            symbol=symbol,
            prices=prices,
            price=price,
            percent=percent,
            signal=signal,
            color=color
        )

    except Exception as e:
        print(e)
        return "Error fetching stock"
# ---------------- DASHBOARD ----------------
@app.route("/dashboard")
@login_required
def dashboard():
    items = Watchlist.query.filter_by(user_id=current_user.id).all()
    watchlist = []

    for item in items:
        if not item.stock:
            continue

        try:
            ticker = yf.Ticker(item.stock)
            data = ticker.history(period="5d")

            if data.empty:
                continue

            close_price = float(data["Close"].iloc[-1])
            open_price = float(data["Open"].iloc[0])

            percent = round(((close_price - open_price) / open_price) * 100, 2)

            watchlist.append({
                "stock": item.stock,
                "price": round(close_price, 2),
                "percent": percent,
                "signal": "BUY" if percent > 0 else "SELL"
            })

        except Exception as e:
            print("Dashboard Error:", e)
            continue

    return render_template("dashboard.html", watchlist=watchlist)

# ---------------- ADD WATCHLIST ----------------
@app.route("/add_watchlist", methods=["POST"])
@login_required
def add_watchlist():
    stock = request.form.get("stock")

    if stock:
        stock = stock.upper().strip()

        exists = Watchlist.query.filter_by(
            user_id=current_user.id,
            stock=stock
        ).first()

        if not exists:
            db.session.add(Watchlist(stock=stock, user_id=current_user.id))
            db.session.commit()
            flash("Added to watchlist ✅", "success")
        else:
            flash("Already added ⚠️", "error")

    return redirect("/dashboard")

# ---------------- REMOVE WATCHLIST ----------------
@app.route("/remove_watchlist", methods=["POST"])
@login_required
def remove_watchlist():
    stock = request.form.get("stock")

    item = Watchlist.query.filter_by(
        user_id=current_user.id,
        stock=stock
    ).first()

    if item:
        db.session.delete(item)
        db.session.commit()
        flash("Removed ❌", "success")

    return redirect("/dashboard")

# ---------------- NEWS ----------------
@app.route("/news")
def news():
    import requests
    from datetime import datetime

    API_KEY = "5ff6e7164b134c859d31e7707e2cbeaa"

    url = f"https://newsapi.org/v2/everything?q=stock%20market&language=en&pageSize=15&sortBy=publishedAt&apiKey={API_KEY}"

    response = requests.get(url)
    data = response.json()

    articles = data.get("articles", [])

    news_data = []

    for a in articles:
        image = a.get("urlToImage")

        # fallback image
        if not image:
            image = "https://via.placeholder.com/400x200?text=Stock+News"

        # format time
        published = a.get("publishedAt", "")
        try:
            time = datetime.strptime(published, "%Y-%m-%dT%H:%M:%SZ")
            time = time.strftime("%d %b • %H:%M")
        except:
            time = "Live Now"

        news_data.append({
            "title": a.get("title"),
            "source": a.get("source", {}).get("name"),
            "url": a.get("url"),
            "image": image,
            "time": time
        })

    return render_template("news.html", news=news_data[:9])

# ---------------- SIMULATOR ----------------
@app.route("/simulator", methods=["GET", "POST"])
def simulator():
    result = None

    if request.method == "POST":
        try:
            buy = float(request.form["buy"])
            sell = float(request.form["sell"])
            qty = int(request.form["qty"])

            result = round((sell - buy) * qty, 2)
        except:
            result = "Invalid input"

    return render_template("simulator.html", result=result)

# ---------------- PROFILE ----------------
@app.route("/profile")
@login_required
def profile():

    # 🔥 Get user history
    history = History.query.filter_by(user_id=current_user.id) \
        .order_by(History.timestamp.desc()).all()

    # 🔥 Stats
    total_viewed = len(history)
    unique_stocks = len(set([h.stock for h in history]))

    # 🔥 Demo profit
    profit = round(total_viewed * 120.5, 2)

    # 🔥 NEW FEATURE: Top Stock
    stocks = [h.stock for h in history]

    top_stock = None
    if stocks:
        top_stock = Counter(stocks).most_common(1)[0][0]

    # 🔥 Send everything to HTML
    return render_template(
        "profile.html",
        history=history,
        total_viewed=total_viewed,
        unique_stocks=unique_stocks,
        profit=profit,
        top_stock=top_stock
    )
# ---------------- UPLOAD PROFILE PIC ----------------
@app.route("/upload_profile", methods=["POST"])
@login_required
def upload_profile():

    file = request.files.get("profile_pic")

    # 🚨 If no file selected
    if not file or file.filename == "":
        print("No file selected")
        return redirect("/profile")

    # 🔥 Secure filename
    filename = secure_filename(file.filename)

    # 🔥 Optional: make filename unique (VERY IMPORTANT)
    filename = f"{current_user.id}_{filename}"

    # 🔥 Save file
    path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(path)

    # 🔥 Save to database
    current_user.profile_pic = filename
    db.session.commit()

    print("Uploaded:", filename)

    return redirect("/profile")
# ---------------- AUTH ----------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(
            username=request.form["username"],
            password=request.form["password"]
        ).first()

        if user:
            login_user(user)
            flash("Login successful", "success")
            return redirect("/dashboard")
        else:
            flash("Invalid credentials", "error")

    return render_template("login.html")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        db.session.add(User(
            username=request.form["username"],
            password=request.form["password"]
        ))
        db.session.commit()
        flash("Signup successful", "success")
        return redirect("/login")

    return render_template("signup.html")

@app.route("/logout")
def logout():
    logout_user()
    return redirect("/")

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)