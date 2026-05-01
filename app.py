from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import pandas as pd
from io import BytesIO
from datetime import datetime
import os
import csv
import io

app = Flask(__name__)
app.secret_key = 'nation-poly-2026-secret-key-secure'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///voting.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'candidate_photos')
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 2MB max

db = SQLAlchemy(app)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ====================== MODELS ======================
class Position(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)

class Candidate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    position_id = db.Column(db.Integer, db.ForeignKey('position.id'), nullable=False)
    photo = db.Column(db.String(200), nullable=True)
    manifesto = db.Column(db.Text, nullable=True)

class Voter(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    student_id = db.Column(db.String(50), unique=True, nullable=False)
    has_voted = db.Column(db.Boolean, default=False)

class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

class Vote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    voter_id = db.Column(db.Integer, db.ForeignKey('voter.id'), nullable=False)
    position_id = db.Column(db.Integer, db.ForeignKey('position.id'), nullable=False)
    candidate_id = db.Column(db.Integer, db.ForeignKey('candidate.id'), nullable=False)
    __table_args__ = (db.UniqueConstraint('voter_id', 'position_id', name='unique_vote_per_position'),)

# ====================== INITIALIZE ======================
with app.app_context():
    db.create_all()
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    if not Admin.query.filter_by(username='admin').first():
        admin = Admin(username='admin', password_hash=generate_password_hash('admin123'))
        db.session.add(admin)
    
    initial_positions = [
        "Chairperson", "Secretary General", "CS Education", "CS Healthy",
        "CS Finance", "CS Sports", "CS Entertainment", "Female Representative"
    ]
    for pos_name in initial_positions:
        if not Position.query.filter_by(name=pos_name).first():
            pos = Position(name=pos_name)
            db.session.add(pos)
    db.session.commit()

# ====================== ROUTES ======================

# Voter Routes
@app.route('/')
def index():
    return redirect(url_for('voter_login'))

@app.route('/voter/login', methods=['GET', 'POST'])
def voter_login():
    if request.method == 'POST':
        name = request.form.get('name')
        student_id = request.form.get('student_id')
        voter = Voter.query.filter_by(name=name, student_id=student_id).first()
        if voter:
            if voter.has_voted:
                flash('You have already voted in this election.', 'warning')
                return redirect(url_for('voter_login'))
            session['voter_id'] = voter.id
            return redirect(url_for('ballot'))
        flash('Invalid Name or Student ID.', 'danger')
    return render_template('voter_login.html')

@app.route('/ballot', methods=['GET', 'POST'])
def ballot():
    if 'voter_id' not in session:
        return redirect(url_for('voter_login'))
    voter = Voter.query.get(session['voter_id'])
    if voter.has_voted:
        session.pop('voter_id', None)
        flash('You have already cast your vote.', 'info')
        return redirect(url_for('voter_login'))
    
    positions = Position.query.all()
    candidates_dict = {pos.id: Candidate.query.filter_by(position_id=pos.id).all() for pos in positions}
    
    if request.method == 'POST':
        for pos in positions:
            candidate_id = request.form.get(f'position_{pos.id}')
            if candidate_id:
                candidate_id = int(candidate_id)
                if not Vote.query.filter_by(voter_id=voter.id, position_id=pos.id).first():
                    vote = Vote(voter_id=voter.id, position_id=pos.id, candidate_id=candidate_id)
                    db.session.add(vote)
        voter.has_voted = True
        db.session.commit()
        session.pop('voter_id', None)
        return redirect(url_for('vote_success'))
    
    return render_template('ballot.html', positions=positions, candidates=candidates_dict)

@app.route('/vote_success')
def vote_success():
    return render_template('vote_success.html')

# Admin Routes
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        admin = Admin.query.filter_by(username=username).first()
        if admin and check_password_hash(admin.password_hash, password):
            session['admin_id'] = admin.id
            return redirect(url_for('admin_dashboard'))
        flash('Invalid admin credentials', 'danger')
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_id', None)
    flash('Logged out successfully', 'success')
    return redirect(url_for('admin_login'))

@app.route('/admin/dashboard')
def admin_dashboard():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
    
    total_registered = Voter.query.count()
    total_voted = Voter.query.filter_by(has_voted=True).count()
    turnout = round((total_voted / total_registered * 100), 2) if total_registered > 0 else 0
    
    positions = Position.query.all()
    position_data = []
    for pos in positions:
        candidates = Candidate.query.filter_by(position_id=pos.id).all()
        labels = [cand.name for cand in candidates]
        votes_data = [Vote.query.filter_by(candidate_id=cand.id).count() for cand in candidates]
        position_data.append({
            'id': pos.id,
            'name': pos.name,
            'labels': labels,
            'data': votes_data
        })
    
    return render_template('admin_dashboard.html',
                         total_registered=total_registered,
                         total_voted=total_voted,
                         turnout=turnout,
                         position_data=position_data)

# Add Position
@app.route('/admin/add_position', methods=['GET', 'POST'])
def add_position():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
    if request.method == 'POST':
        name = request.form.get('name')
        if name and not Position.query.filter_by(name=name).first():
            pos = Position(name=name)
            db.session.add(pos)
            db.session.commit()
            flash(f'Position "{name}" added successfully!', 'success')
            return redirect(url_for('admin_dashboard'))
        flash('Position already exists.', 'danger')
    return render_template('add_position.html')

# Add Single Voter
@app.route('/admin/add_voter', methods=['GET', 'POST'])
def add_voter():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
    if request.method == 'POST':
        name = request.form.get('name')
        student_id = request.form.get('student_id')
        if name and student_id and not Voter.query.filter_by(student_id=student_id).first():
            voter = Voter(name=name, student_id=student_id)
            db.session.add(voter)
            db.session.commit()
            flash('Voter added successfully!', 'success')
        else:
            flash('Student ID already exists or fields are empty.', 'danger')
    return render_template('add_voter.html')

# Bulk Voters
@app.route('/admin/bulk_voters', methods=['GET', 'POST'])
def bulk_voters():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file uploaded', 'danger')
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '' or not file.filename.endswith('.csv'):
            flash('Please upload a valid .csv file', 'danger')
            return redirect(request.url)
        
        try:
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            csv_input = csv.reader(stream)
            next(csv_input)  # skip header
            added = 0
            for row in csv_input:
                if len(row) >= 2:
                    name = row[0].strip()
                    student_id = row[1].strip()
                    if name and student_id and not Voter.query.filter_by(student_id=student_id).first():
                        voter = Voter(name=name, student_id=student_id)
                        db.session.add(voter)
                        added += 1
            db.session.commit()
            flash(f'{added} voters added successfully!', 'success')
        except:
            flash('Error processing CSV file.', 'danger')
    return render_template('bulk_voters.html')

# Manage Candidates
@app.route('/admin/position/<int:pos_id>/candidates', methods=['GET', 'POST'])
def manage_candidates(pos_id):
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
    pos = Position.query.get_or_404(pos_id)
    if request.method == 'POST':
        name = request.form.get('name')
        manifesto = request.form.get('manifesto')
        photo_file = request.files.get('photo')
        photo_path = None
        
        if photo_file and photo_file.filename and allowed_file(photo_file.filename):
            filename = secure_filename(photo_file.filename)
            photo_path = f'candidate_photos/{filename}'
            photo_file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        
        if name and not Candidate.query.filter_by(name=name, position_id=pos_id).first():
            cand = Candidate(name=name, position_id=pos_id, photo=photo_path, manifesto=manifesto)
            db.session.add(cand)
            db.session.commit()
            flash(f'Candidate "{name}" added!', 'success')
    
    candidates = Candidate.query.filter_by(position_id=pos_id).all()
    return render_template('manage_candidates.html', pos=pos, candidates=candidates)

# Edit Candidate
@app.route('/admin/candidate/edit/<int:cand_id>', methods=['GET', 'POST'])
def edit_candidate(cand_id):
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
    cand = Candidate.query.get_or_404(cand_id)
    if request.method == 'POST':
        name = request.form.get('name')
        manifesto = request.form.get('manifesto')
        photo_file = request.files.get('photo')
        
        if name:
            cand.name = name
        if manifesto is not None:
            cand.manifesto = manifesto
        if photo_file and photo_file.filename and allowed_file(photo_file.filename):
            filename = secure_filename(photo_file.filename)
            photo_path = f'candidate_photos/{filename}'
            photo_file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            cand.photo = photo_path
        
        db.session.commit()
        flash('Candidate updated successfully!', 'success')
        return redirect(url_for('manage_candidates', pos_id=cand.position_id))
    
    return render_template('edit_candidate.html', cand=cand)

# Delete Candidate
@app.route('/admin/candidate/delete/<int:cand_id>')
def delete_candidate(cand_id):
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
    cand = Candidate.query.get_or_404(cand_id)
    pos_id = cand.position_id
    db.session.delete(cand)
    db.session.commit()
    flash('Candidate deleted!', 'danger')
    return redirect(url_for('manage_candidates', pos_id=pos_id))

# Reset All Votes
@app.route('/admin/reset_votes', methods=['POST'])
def reset_votes():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
    Vote.query.delete()
    Voter.query.update({Voter.has_voted: False})
    db.session.commit()
    flash('All votes have been reset successfully!', 'success')
    return redirect(url_for('admin_dashboard'))

# Voters List
@app.route('/admin/voters')
def voters_list():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
    voters = Voter.query.all()
    return render_template('voters_list.html', voters=voters)

# Export Excel
@app.route('/admin/export/<int:position_id>')
def export_position(position_id):
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
    pos = Position.query.get_or_404(position_id)
    candidates = Candidate.query.filter_by(position_id=position_id).all()
    
    data = []
    total_votes = 0
    for cand in candidates:
        votes = Vote.query.filter_by(candidate_id=cand.id).count()
        data.append({'Candidate': cand.name, 'Votes': votes})
        total_votes += votes
    
    for row in data:
        row['Percentage (%)'] = round((row['Votes'] / total_votes * 100), 2) if total_votes > 0 else 0
    
    df = pd.DataFrame(data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name=pos.name[:31])
    output.seek(0)
    
    filename = f"{pos.name.replace(' ', '_')}_Results_{datetime.now().strftime('%Y%m%d')}.xlsx"
    return send_file(output, download_name=filename, as_attachment=True, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

if __name__ == '__main__':
    print("🚀 Nation Polytechnic & University Voting System is running...")
    print("→ Admin: http://127.0.0.1:5000/admin/login")
    print("→ Voter: http://127.0.0.1:5000")
    app.run(debug=True, port=5000)