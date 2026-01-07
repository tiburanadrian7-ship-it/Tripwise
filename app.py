from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import os
from flask import Blueprint
from dotenv import load_dotenv
import google.generativeai as genai
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
import re
from datetime import datetime 

# ========== CONFIGURATION ==========
load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "tripwise_secret_key")

from dotenv import load_dotenv
import os

load_dotenv(override=True) 

API_KEY = os.getenv("GOOGLE_API_KEY")
genai.configure(api_key=API_KEY)

# Ensure you use a supported model name
chat_model = genai.GenerativeModel("gemini-2.5-flash")

# Database
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DATABASE_URI", 'mysql+pymysql://root:@localhost/tripwise')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ========== MODELS (MATCHING SQL SCHEMA) ==========

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column('user_id', db.Integer, primary_key=True)
    name = db.Column('full_name', db.String(255), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=True)
    phone = db.Column(db.String(50), nullable=True)
    password_hash = db.Column('password', db.String(255), nullable=True)
    role = db.Column(db.String(20), default='user')  # 👈 ADD THIS


class Island(db.Model):
    __tablename__ = 'islands'
    id = db.Column('island_id', db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    # FIX: Mapped to 'island_image' from previous step
    image = db.Column('island_image', db.String(255), nullable=False)
    description = db.Column(db.Text)
    location = db.Column(db.String(255))
    region = db.Column(db.String(100))
    history = db.Column(db.Text) 
    map_coordinates = db.Column(db.String(255))
    
    @property
    def latitude(self):
        if self.map_coordinates:
            try:
                return float(self.map_coordinates.split(',')[0].strip())
            except:
                return None
        return None
    
    @property
    def longitude(self):
        if self.map_coordinates:
            try:
                return float(self.map_coordinates.split(',')[1].strip())
            except:
                return None
        return None

    @property
    def details(self):
        return self.history


class Establishment(db.Model):
    __tablename__ = 'establishments'

    establishment_id = db.Column('establishment_id', db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    type = db.Column(db.Enum('hotel','bar','restaurant'), nullable=False)
    island_id = db.Column(db.Integer, db.ForeignKey('islands.island_id'))
    location = db.Column(db.String(255))
    contact_number = db.Column(db.String(50))
    opening_hours = db.Column(db.String(100))
    description = db.Column(db.Text)
    rating = db.Column(db.Float)
    establishments_image = db.Column(db.String(255), nullable=False)
    official_website = db.Column(db.String(255))
    

    owner_id = db.Column(db.Integer, db.ForeignKey('users.user_id'))
    is_approved = db.Column(db.Boolean, default=False)
    rejected_reason = db.Column(db.String(255))

    created_at = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime)

    @property
    def category(self):
        return self.type
    
    @property
    def id(self):
        return self.establishment_id


class Visit(db.Model):
    __tablename__ = 'visits'
    id = db.Column('visit_id', db.Integer, primary_key=True)
    island_id = db.Column(db.Integer, db.ForeignKey('islands.island_id'), nullable=False)
    visit_week = db.Column('visit_week', db.Date, nullable=False) 
    visit_month = db.Column('visit_month', db.Date, nullable=False)
    visit_year = db.Column('visit_year', db.Date, nullable=False)
    total_visits = db.Column('total_visit', db.Integer, nullable=False)
    island = db.relationship('Island', backref='visits')

from datetime import datetime

class Booking(db.Model):
    __tablename__ = "bookings"

    booking_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)
    establishment_id = db.Column(db.Integer, db.ForeignKey("establishments.establishment_id"), nullable=False)
    
    check_in_date = db.Column(db.Date, nullable=False)
    check_out_date = db.Column(db.Date, nullable=True)
    guests = db.Column(db.Integer, nullable=False)
    notes = db.Column(db.Text, nullable=True)

    status = db.Column(db.String(20), default="pending")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)




# ========== DATABASE INIT (Updated with new Establishment fields) ==========
def init_db():
    print("Initializing MySQL Database...")
    try:
        with app.app_context():
            db.create_all() 
            print("✅ MySQL tables created or already exist.")

            # --- Island Data ---
            if not Island.query.first():
                sample_islands = [
                    Island(name='Alaminos Hundred Islands', image='hundred_islands.jpg', 
                            description='Famous national park with over 100 islands',
                            history='Protected area since 1940',
                            location='Alaminos', region='Pangasinan',
                            map_coordinates='16.1622,120.3621'), # ID 1
                    Island(name='Quezon Island', image='quezon_island.jpg',
                            description='Popular island for day trips',
                            history='Named after President Quezon',
                            location='Alaminos', region='Pangasinan',
                            map_coordinates='16.1660,120.3640'), # ID 2
                    Island(name='Imelda Island', image='imelda_island.jpg',
                            description='Small lodging and beach',
                            history='Named after Imelda Marcos',
                            location='Alaminos', region='Pangasinan',
                            map_coordinates='16.1680,120.3660') # ID 3
                ]
                db.session.add_all(sample_islands)
                db.session.commit()
                print("✅ Sample island data added.")

            # --- Establishment Data (Updated with image and other new fields) ---
            if not Establishment.query.first():
                sample_establishments = [
                    Establishment(name='Quezon Beach Resort', description='Beachfront resort',
                                        type='hotel', island_id=2, 
                                        image='quezon_resort.jpg', # NEW FIELD
                                        location='Quezon Island, Alaminos', # NEW FIELD
                                        rating=4.5, opening_hours='24/7'), # NEW FIELD
                    Establishment(name='Imelda Resort', description='Small cozy resort',
                                        type='hotel', island_id=3,
                                        image='imelda_resort.jpg', # NEW FIELD
                                        location='Imelda Island, Alaminos', # NEW FIELD
                                        rating=4.2, contact_number='09123456789'), # NEW FIELD
                    Establishment(name='Island Bar & Grill', description='Beachside bar and restaurant',
                                        type='bar', island_id=1,
                                        image='island_bar.jpg', # NEW FIELD
                                        location='Governor\'s Island, Alaminos', # NEW FIELD
                                        opening_hours='10:00 AM - 10:00 PM', rating=4.0) # NEW FIELD
                ]
                db.session.add_all(sample_establishments)
                db.session.commit()
                print("✅ Sample establishment data added.")

            # --- Visit Data ---
            if not Visit.query.first():
                def get_visit_data(island_id, week_day, total):
                    return Visit(
                        island_id=island_id, 
                        visit_week=date(2025, 11, week_day), 
                        visit_month=date(2025, 11, 1), 
                        visit_year=date(2025, 1, 1), 
                        total_visits=total
                    )
                
                sample_visits = [
                    get_visit_data(island_id=1, week_day=17, total=120),
                    get_visit_data(island_id=2, week_day=17, total=95),
                    get_visit_data(island_id=3, week_day=17, total=150),
                    get_visit_data(island_id=1, week_day=10, total=130),
                    get_visit_data(island_id=2, week_day=10, total=85),
                    get_visit_data(island_id=3, week_day=10, total=160)
                ]
                db.session.add_all(sample_visits)
                db.session.commit()
                print("✅ Sample visit data added.")
            
        print("✅ Database OK")
    except Exception as e:
        print(f"Database Error: {e}")
        print("ACTION NEEDED: Ensure MySQL/XAMPP is running and the 'tripwise' database exists and credentials are correct.")


init_db()

# ==========================================================
# FIX: DEFINE THE MISSING HELPER FUNCTION HERE
# ==========================================================
def get_place_by_id(place_id):
    """Fetches an Establishment object by its ID using Flask-SQLAlchemy."""
    # Establishment is your model for places
    return Establishment.query.get_or_404(place_id)
# ==========================================================

# ========== CHATBOT (Unchanged) ==========

def get_db_context(user_message):
    """Fetch relevant islands, establishments, and visit data without IDs."""
    
    # 1. Initialize context at the very beginning
    context = ""
    
    # 2. Query data
    islands = Island.query.filter(Island.name.ilike(f"%{user_message}%")).all()
    establishments = Establishment.query.filter(
        (Establishment.name.ilike(f"%{user_message}%")) |
        (Establishment.type.ilike(f"%{user_message}%"))
    ).all()

    # Fallback: If user didn't specify an island, provide the full list
    if not islands:
        islands = Island.query.all()
        
    # 3. Build Island Section with Numbering
    if islands:
        context += "Available Islands (Numbered List):\n"
        for index, i in enumerate(islands, start=1):
            # No IDs or asterisks here
            context += f"{index}. {i.name}: {i.description}. (Location: {i.latitude}, {i.longitude})\n"
            
    # 4. Build Establishments Section
    if establishments:
        context += "\nPlaces to Stay & Eat:\n"
        for p in establishments:
            island_name = "Mainland"
            if p.island_id:
                island = Island.query.get(p.island_id)
                island_name = island.name if island else "Unknown"
            
            context += f"- {p.name} ({p.category}) at {island_name}: {p.description}\n"
            
    # 5. Add Visit Data
    total_visits_data = db.session.query(
        Visit.island_id,
        db.func.sum(Visit.total_visits).label('annual_visits')
    ).filter(
        Visit.visit_month.between('2025-01-01', '2025-12-31') 
    ).group_by(Visit.island_id).order_by(db.desc('annual_visits')).all()

    if total_visits_data:
        context += "\nIsland Popularity Ranking:\n"
        for island_id, annual_visits in total_visits_data:
            island = Island.query.get(island_id)
            if island:
                context += f"- {island.name}: {annual_visits:,} visitors per year.\n"
                
    return context


def link_islands_places(text):
    """Replace island/place names in AI-generated text with clickable links."""
    islands = Island.query.all()
    establishments = Establishment.query.all()

    for obj_list, base_url in [(islands, '/island/'), (establishments, '/place/')]:
        sorted_list = sorted(obj_list, key=lambda x: len(x.name), reverse=True)
        for obj in sorted_list:
            pattern = r'\b' + re.escape(obj.name) + r'\b'
            text = re.sub(pattern, f"<a href='{base_url}{obj.id}'>{obj.name}</a>", text)

    return text

@app.route("/ask", methods=["POST"])
def ask():
    data = request.json
    user_message = data.get("message", "").strip()
    if not user_message:
        return jsonify({"response": "⚠️ Please type a message."})

    with app.app_context():
        db_context = get_db_context(user_message)
    
    prompt = f"""
You are WiseBot, a friendly travel assistant specializing in Philippine destinations.
Use the following information, especially the visitor statistics, to provide helpful suggestions to the user.
Do not mention the source of your information.

Information:
{db_context}

User: {user_message}
AI:
"""
    try:
        response = chat_model.generate_content(prompt)
        linked_response = link_islands_places(response.text)
        return jsonify({"response": linked_response})
    except Exception as e:
        return jsonify({"response": f"⚠️ Chat error: {str(e)}"})

# ========== ROUTES (Unchanged as they rely on the 'image' attribute, which is now mapped) ==========
@app.route("/")
def index():
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        pwd = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password_hash, pwd):
            session.clear()
            session["user_id"] = user.id
            session["role"] = user.role

            flash(f"Welcome back, {user.name}!", "success")

            # 🔀 ROLE-BASED REDIRECT
            if user.role == "admin":
                return redirect(url_for("admin_dashboard"))
            elif user.role == "owner":
                return redirect(url_for("owner_dashboard"))
            else:
                return redirect(url_for("home"))


        flash("Invalid email or password", "danger")

    return render_template("login.html")

@app.route("/owner/dashboard")
def owner_dashboard():
    if "role" not in session or session["role"] != "owner":
        flash("Access denied", "danger")
        return redirect(url_for("login"))

    owner = User.query.get(session["user_id"])

    establishments = Establishment.query.filter_by(
        owner_id=owner.id
    ).all()

    return render_template(
        "owner_dashboard.html",
        owner=owner,
        establishments=establishments
    )

@app.route("/owner/establishment/add", methods=["GET", "POST"])
def add_establishment():
    if session.get("role") != "owner":
        flash("Access denied", "danger")
        return redirect(url_for("login"))

    if request.method == "POST":
        est = Establishment(
            name=request.form["name"],
            type=request.form["type"],
            location=request.form["location"],
            description=request.form["description"],
            contact_number=request.form["contact"],
            opening_hours=request.form["hours"],
            establishments_image=request.form["image"],
            owner_id=session["user_id"],
            is_approved=0
        )

        db.session.add(est)
        db.session.commit()

        flash("Establishment submitted for approval", "success")
        return redirect(url_for("owner_dashboard"))

    return render_template("owner_add_establishment.html")

@app.route("/owner/establishment/delete/<int:id>", methods=["POST"])
def delete_establishment(id):
    if "user_id" not in session:
        flash("Please log in first.", "danger")
        return redirect(url_for("login"))

    owner = User.query.get(session["user_id"])

    if owner.role != "owner":
        flash("Unauthorized access.", "danger")
        return redirect(url_for("home"))

    est = Establishment.query.filter_by(
        id=id,
        owner_id=owner.id
    ).first_or_404()

    db.session.delete(est)
    db.session.commit()

    flash("Establishment deleted successfully.", "success")
    return redirect(url_for("owner_dashboard"))

from sqlalchemy import func

@app.route("/admin/reports")
def admin_reports():
    if session.get("role") != "admin":
        flash("Access denied", "danger")
        return redirect(url_for("login"))

    # Bookings summary
    bookings_summary = {
        'pending': db.session.query(func.count(Booking.booking_id)).filter_by(status='pending').scalar(),
        'confirmed': db.session.query(func.count(Booking.booking_id)).filter_by(status='confirmed').scalar(),
        'cancelled': db.session.query(func.count(Booking.booking_id)).filter_by(status='cancelled').scalar(),
    }

    # Top islands
    top_islands = db.session.query(
        Island.name, func.sum(Visit.total_visits).label('total')
    ).join(Visit).group_by(Island.id).order_by(func.sum(Visit.total_visits).desc()).limit(5).all()

    # Top establishments
    top_establishments = db.session.query(
        Establishment.name, func.count(Booking.booking_id).label('total')
    ).join(Booking, Booking.establishment_id == Establishment.establishment_id)\
     .group_by(Establishment.establishment_id)\
     .order_by(func.count(Booking.booking_id).desc())\
     .limit(5).all()

    return render_template(
        "admin_reports.html",
        bookings_summary=bookings_summary,
        top_islands=top_islands,
        top_establishments=top_establishments
    )

# Update user role
@app.route("/admin/user/edit/<int:user_id>", methods=["POST"])
def edit_user_role(user_id):
    if session.get("role") != "admin":
        flash("Access denied", "danger")
        return redirect(url_for("login"))

    user = User.query.get_or_404(user_id)
    new_role = request.form.get("role")
    if new_role in ["user", "owner", "admin"]:
        user.role = new_role
        db.session.commit()
        flash("User role updated.", "success")
    else:
        flash("Invalid role.", "danger")
    return redirect(url_for("manage_users"))

# Delete user
@app.route("/admin/user/delete/<int:user_id>", methods=["POST"])
def delete_user(user_id):
    if session.get("role") != "admin":
        flash("Access denied", "danger")
        return redirect(url_for("login"))

    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    flash("User deleted.", "success")
    return redirect(url_for("manage_users"))

# Main route to display page
@app.route("/admin/manage_users")
def manage_users():
    if session.get("role") != "admin":
        flash("Access denied", "danger")
        return redirect(url_for("login"))
    users = User.query.all()
    return render_template("admin_manage_users.html", users=users)

@app.route("/admin/manage_users")
def admin_manage_users():
    if session.get("role") != "admin":
        flash("Access denied", "danger")
        return redirect(url_for("login"))

    users = User.query.order_by(User.id.desc()).all()

    return render_template("admin_manage_users.html", users=users)

@app.route("/admin/user/delete/<int:user_id>", methods=["POST"])
def admin_delete_user(user_id):
    if session.get("role") != "admin":
        flash("Access denied", "danger")
        return redirect(url_for("login"))

    user = User.query.get_or_404(user_id)

    # Prevent deleting yourself
    if user.user_id == session["user_id"]:
        flash("You cannot delete your own account.", "warning")
        return redirect(url_for("admin_manage_users"))

    # 👉 ADD THESE TWO LINES FIRST
    Transaction.query.filter_by(booking_id=user_id).delete()
    Booking.query.filter_by(user_id=user_id).delete()

    db.session.delete(user)
    db.session.commit()

    flash("User and related records deleted successfully.", "success")
    return redirect(url_for("admin_manage_users"))


@app.route("/admin/user/edit/<int:user_id>", methods=["GET", "POST"])
def admin_edit_user(user_id):
    if session.get("role") != "admin":
        flash("Access denied", "danger")
        return redirect(url_for("login"))

    user = User.query.get_or_404(user_id)

    if request.method == "POST":
        new_role = request.form.get("role")

        if new_role not in ["user", "owner", "admin"]:
            flash("Invalid role selected.", "danger")
            return redirect(request.url)

        user.role = new_role
        db.session.commit()

        flash("User updated successfully.", "success")
        return redirect(url_for("admin_manage_users"))

    return render_template("admin_edit_user.html", user=user)



@app.route("/admin/dashboard")
def admin_dashboard():
    if session.get("role") != "admin":
        flash("Access denied", "danger")
        return redirect(url_for("login"))

    pending_establishments = Establishment.query.filter_by(
        is_approved=0
    ).all()

    return render_template(
        "admin_dashboard.html",
        establishments=pending_establishments
    )

@app.route("/owner/establishment/edit/<int:id>", methods=["GET", "POST"])
def edit_establishment(id):
    if session.get("role") != "owner":
        flash("Access denied", "danger")
        return redirect(url_for("login"))

    est = Establishment.query.filter_by(
        id=id,
        owner_id=session["user_id"]
    ).first_or_404()

    if request.method == "POST":
        est.name = request.form["name"]
        est.type = request.form["type"]
        est.location = request.form["location"]
        est.contact_number = request.form["contact_number"]
        est.opening_hours = request.form["opening_hours"]
        est.description = request.form["description"]

        db.session.commit()
        flash("Establishment updated successfully", "success")
        return redirect(url_for("owner_dashboard"))

    return render_template("edit_establishment.html", est=est)


@app.route("/admin/approve/<int:id>")
def approve_establishment(id):
    if session.get("role") != "admin":
        abort(403)

    est = Establishment.query.get_or_404(id)
    est.is_approved = 1
    est.rejected_reason = None

    db.session.commit()
    flash("Establishment approved", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/reject/<int:id>", methods=["POST"])
def reject_establishment(id):
    if session.get("role") != "admin":
        abort(403)

    est = Establishment.query.get_or_404(id)
    est.is_approved = 0
    est.rejected_reason = request.form["reason"]

    db.session.commit()
    flash("Establishment rejected", "warning")
    return redirect(url_for("admin_dashboard"))



@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        pwd = request.form.get("password", "")
        cpwd = request.form.get("confirm_password", "")

        if User.query.filter_by(email=email).first():
            flash("Email already exists", "warning")
        elif pwd != cpwd:
            flash("Passwords do not match", "danger")
        else:
            try:
                new_user = User(name=name, email=email, password_hash=generate_password_hash(pwd))
                db.session.add(new_user)
                db.session.commit()
                flash("Account created! You can now log in.", "success")
                return redirect(url_for("login"))
            except Exception as e:
                db.session.rollback()
                flash(f"Database error during sign up: {e}", "danger")
    return render_template("signup.html")


@app.route("/plan_trip", methods=["GET", "POST"])
def plan_trip():
    if "user_id" not in session:
        return redirect(url_for("login"))

    destinations_list = Island.query.all()

    if request.method == "POST":
        destination_ids = request.form.getlist("destinations")
        if not destination_ids:
            flash("Please select at least one destination.", "danger")
            return redirect(url_for("plan_trip"))

        try:
            budget_per_person = float(request.form.get("budget"))
            days = int(request.form.get("days"))
            people = int(request.form.get("people"))
        except (ValueError, TypeError):
            flash("Invalid numeric input for budget, days, or number of people.", "danger")
            return redirect(url_for("plan_trip"))

        selected_islands = Island.query.filter(Island.id.in_(destination_ids)).all()
        if not selected_islands:
            flash("Selected islands not found.", "danger")
            return redirect(url_for("plan_trip"))

        establishments = Establishment.query.filter(
            Establishment.island_id.in_([i.id for i in selected_islands])
        ).all()

        db_context = ""
        for island in selected_islands:
            db_context += f"Island: {island.name}\nDescription: {island.description}\nDetails: {island.details}\n\n"
            island_establishments = [p for p in establishments if p.island_id == island.id]
            if island_establishments:
                db_context += "Places:\n"
                for p in island_establishments:
                    db_context += f"- {p.name} ({p.category}): {p.description}\n"
            db_context += "\n"

        islands_names = ", ".join([i.name for i in selected_islands])

        plan_prompt = (
            f"You are a Philippine travel expert. Create a detailed, day-by-day travel itinerary "
            f"for a trip to: {islands_names}. The trip length is exactly {days} days, for {people} people, "
            f"with a budget of PHP {budget_per_person} per person.\n\n"
            f"Use the following information about islands and places:\n{db_context}\n"
            "Include local food, transport, and estimated cost per day per person. "
            "Use Markdown and Day headers."
        )

        try:
            response = chat_model.generate_content(plan_prompt)
            itinerary = response.text

            day_splits = re.split(r'Day\s+\d+[:.\s]*', itinerary, flags=re.IGNORECASE)
            filtered_itinerary = ""

            for i in range(1, min(days + 1, len(day_splits))):
                filtered_itinerary += f"Day {i}\n{day_splits[i].strip()}\n\n"

            return render_template(
                "plan_result.html",
                destination=islands_names,
                itinerary=filtered_itinerary.strip(),
                budget=budget_per_person,
                days=days,
                people=people
            )

        except Exception as e:
            flash(f"Error generating plan: {e}", "danger")
            return redirect(url_for("plan_trip"))

    return render_template("plan_trip.html", destinations=destinations_list)


@app.route("/home")
def home():
    # 🔐 Role-based protection
    if "role" not in session or session["role"] != "user":
        return redirect(url_for("login"))

    # Get user by ID (more secure than email)
    user_data = User.query.get(session["user_id"])
    if not user_data:
        session.clear()
        return redirect(url_for("login"))

    # Top 10 Islands by visits
    top_islands_data = db.session.query(
        Island.id,
        Island.name,
        Island.image,
        db.func.sum(Visit.total_visits).label('annual_visits')
    ).join(Visit, Island.id == Visit.island_id).filter(
        Visit.visit_month.between('2025-01-01', '2025-12-31')
    ).group_by(Island.id, Island.name, Island.image).order_by(
        db.desc('annual_visits')
    ).limit(10).all()

    islands = Island.query.all()
    establishments = Establishment.query.filter_by(is_approved=1).all()


    return render_template(
        "home.html",
        user=user_data.name,
        islands=islands,
        places=establishments,
        top_islands=top_islands_data
    )



from sqlalchemy import text # Ensure this import is at the top of app.py
# Place this above your @app.route definitions
class Activity(db.Model):
    __tablename__ = 'activities'
    activity_id = db.Column(db.Integer, primary_key=True)
    island_id = db.Column(db.Integer, db.ForeignKey('islands.island_id'))
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Float)
    created_datetime_id = db.Column(db.Integer)
    updated_datetime_id = db.Column(db.Integer)

@app.route('/island/<int:island_id>')
def island_details(island_id):
    # 1. Fetch the specific island
    island = Island.query.get_or_404(island_id)
    
    # 2. FIX: Fetch only activities belonging to THIS island_id
    # This prevents the list from displaying activities from every island in your DB
    # Use this if your database table itself contains duplicate entries
    activities = Activity.query.filter_by(island_id=island_id).group_by(Activity.name).all()
    
    # 3. Fetch establishments for this island
    establishments = Establishment.query.filter_by(island_id=island_id).all()
    
    return render_template("island_details.html", 
                           island=island, 
                           places=establishments, 
                           activities=activities)
# --- ROUTE TO DELETE A BOOKING ---
@app.route('/delete_booking/<int:booking_id>', methods=['POST'])
def delete_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    
    # Optional: Check if the booking belongs to the current user
    # if booking.user_id != session.get('user_id'):
    #     return "Unauthorized", 403

    db.session.delete(booking)
    db.session.commit()
    return redirect(url_for('my_bookings'))

@app.route('/view_booking/<int:booking_id>')
def view_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    # Ensure 'Establishment' matches your table model name
    place = Establishment.query.get(booking.establishment_id) 
    return render_template('view_booking.html', booking=booking, place=place)

# --- ROUTE TO EDIT A BOOKING ---
@app.route('/edit_booking/<int:booking_id>', methods=['GET', 'POST'])
def edit_booking(booking_id):
    # Fetch the specific booking from the database using its primary key
    booking = Booking.query.get_or_404(booking_id)
    
    if request.method == 'POST':
        # 1. Capture the new data from the form
        booking.check_in_date = request.form.get('check_in_date')
        booking.check_out_date = request.form.get('check_out_date')
        booking.guests = request.form.get('guests')
        booking.notes = request.form.get('notes')
        
        # 2. Save changes to the database
        db.session.commit()
        
        # 3. Go back to the list
        return redirect(url_for('my_bookings'))

    # If it's a GET request, just show the card with the existing info
    return render_template('edit_booking.html', booking=booking)

@app.route("/place/<int:place_id>")
def place_details(place_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    establishment = Establishment.query.get_or_404(place_id)
    return render_template("place_details.html", place=establishment)

@app.route("/my-bookings")
def my_bookings():
    if session.get("role") != "user":
        return redirect(url_for("login"))

    bookings = (
    db.session.query(Booking, Establishment)
    .join(Establishment, Booking.establishment_id == Establishment.establishment_id)
    .filter(Booking.user_id == session["user_id"])
    .order_by(Booking.booking_id.desc())
    .all()
    )


    return render_template(
        "my_bookings.html",
        bookings=bookings
    )

@app.route("/owner/bookings")
def owner_bookings():
    if "user_id" not in session:
        return redirect(url_for("login"))

    owner_id = session["user_id"]

    owner_establishments = Establishment.query.filter_by(owner_id=owner_id).all()

    est_ids = [e.establishment_id for e in owner_establishments]

    bookings = Booking.query.filter(Booking.establishment_id.in_(est_ids))\
        .order_by(Booking.booking_id.desc()).all()

    return render_template("owner_bookings.html", bookings=bookings)



@app.route("/owner/booking/accept/<int:booking_id>")
def accept_booking(booking_id):
    owner_id = session["user_id"]

    booking = Booking.query.get_or_404(booking_id)

    establishment = Establishment.query.get(booking.establishment_id)

    if establishment.owner_id != owner_id:
        flash("Unauthorized action","danger")
        return redirect(url_for("owner_bookings"))

    booking.status = "confirmed"
    db.session.commit()

    flash("Booking confirmed","success")
    return redirect(url_for("owner_bookings"))


@app.route('/owner/approve_booking/<int:booking_id>')
def owner_approve_booking(booking_id):
    if 'owner_id' not in session:
        return redirect(url_for('login'))

    booking = Booking.query.get_or_404(booking_id)

    booking.status = 'approved'
    db.session.commit()

    return redirect(url_for('owner_bookings'))


@app.route("/owner/booking/reject/<int:booking_id>")
def reject_booking(booking_id):
    owner_id = session["user_id"]

    booking = Booking.query.get_or_404(booking_id)

    establishment = Establishment.query.get(booking.establishment_id)

    if establishment.owner_id != owner_id:
        flash("Unauthorized action","danger")
        return redirect(url_for("owner_bookings"))

    booking.status = "cancelled"
    db.session.commit()

    flash("Booking cancelled","info")
    return redirect(url_for("owner_bookings"))




@app.route('/book_place/<int:place_id>', methods=['GET', 'POST'])
def book_place(place_id):
    if session.get("role") != "user":
        flash("Please log in as a user to book.", "warning")
        return redirect(url_for("login"))

    place = Establishment.query.get_or_404(place_id)

    if request.method == 'POST':
        check_in = request.form.get('check_in_date')
        check_out = request.form.get('check_out_date')
        guests = request.form.get('guests')
        notes = request.form.get('notes')

        # 🔐 Basic validation
        if not check_in or not check_out or not guests:
            flash("All fields are required.", "danger")
            return redirect(request.url)

        # ✅ CREATE BOOKING RECORD
        booking = Booking(
        user_id=session["user_id"],
        establishment_id=place.id,
        check_in_date=datetime.strptime(check_in, "%Y-%m-%d").date(),
        check_out_date=datetime.strptime(check_out, "%Y-%m-%d").date() if check_out else None,
        guests=int(guests),
        notes=notes,
        status="pending"
        )
        db.session.add(booking)
        db.session.commit()


        flash("Booking submitted and pending approval.", "success")
        return redirect(url_for("my_bookings"))

    return render_template('booking.html', place=place)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ========== RUN ==========
if __name__ == "__main__":
    app.run(debug=True)