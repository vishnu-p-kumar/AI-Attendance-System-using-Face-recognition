import os
import shutil
from flask import Flask, render_template, request, redirect, session, make_response, url_for
import sqlite3
import pickle
from io import StringIO
import csv
import datetime
from database import init_db
from face_recog import capture_face_encoding, run_live_attendance

app = Flask(__name__)
app.secret_key = "face_attendance_secret"
init_db()

# ---------- LOGIN ----------
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        role = request.form.get("role")
        username = request.form.get("username")
        password = request.form.get("password")
        conn = sqlite3.connect('attendance.db')
        c = conn.cursor()
        if role == "admin":
            c.execute("SELECT * FROM admin WHERE username=? AND password=?", (username, password))
        elif role == "student":
            c.execute("SELECT * FROM students WHERE usn=? AND dob=?", (username, password))
        else:
            conn.close()
            return "Invalid role"
        user = c.fetchone()
        conn.close()
        if user:
            session["username"] = username
            session["role"] = role
            return redirect("/dashboard")
        else:
            return "Invalid credentials"
    return render_template("login.html")

# ---------- DASHBOARD ----------
@app.route("/dashboard")
def dashboard():
    if "username" not in session:
        return redirect("/")
    if session["role"] == "admin":
        return render_template("admin_dashboard.html")

    usn = session["username"]
    conn = sqlite3.connect('attendance.db')
    c = conn.cursor()
    c.execute("SELECT class_id FROM students WHERE usn=?", (usn,))
    class_row = c.fetchone()
    current_subject, current_status = None, None
    if class_row:
        class_id = class_row[0]
        now = datetime.datetime.now().time()
        c.execute("SELECT subject, start_time, end_time FROM timetable WHERE class_id=?", (class_id,))
        for subject, start_str, end_str in c.fetchall():
            start_time = datetime.datetime.strptime(start_str, "%H:%M").time()
            end_time = datetime.datetime.strptime(end_str, "%H:%M").time()
            if start_time <= now <= end_time:
                current_subject = subject
                break
        if current_subject:
            c.execute("SELECT id FROM students WHERE usn=?", (usn,))
            student_id = c.fetchone()[0]
            today_str = datetime.date.today().strftime("%Y-%m-%d")
            c.execute("SELECT status FROM attendance WHERE student_id=? AND subject=? AND date=?",
                      (student_id, current_subject, today_str))
            row = c.fetchone()
            current_status = row[0] if row else "Absent"
    c.execute("""
        SELECT DISTINCT subject FROM attendance
        JOIN students ON attendance.student_id = students.id
        WHERE students.usn=?
    """, (usn,))
    subjects = [s[0] for s in c.fetchall()]
    conn.close()
    return render_template("student_dashboard.html",
                           usn=usn,
                           current_subject=current_subject,
                           current_status=current_status,
                           subjects=subjects)

# ---------- CLASS MANAGEMENT ----------
@app.route("/classes")
def classes():
    conn = sqlite3.connect('attendance.db')
    c = conn.cursor()
    c.execute("SELECT id, class_name FROM classes")
    classes = c.fetchall()
    conn.close()
    return render_template("classes.html", classes=classes)

@app.route("/add_class", methods=["POST"])
def add_class():
    class_name = request.form["class_name"]
    conn = sqlite3.connect('attendance.db')
    c = conn.cursor()
    c.execute("INSERT INTO classes (class_name) VALUES (?)", (class_name,))
    conn.commit()
    conn.close()
    return redirect("/classes")

# ---------- TIMETABLE ----------
@app.route("/timetable")
def timetable():
    selected_class_id = request.args.get("class_id")
    conn = sqlite3.connect('attendance.db')
    c = conn.cursor()
    c.execute("SELECT id, class_name FROM classes")
    classes = c.fetchall()
    timetable = []
    if selected_class_id:
        c.execute("""
            SELECT timetable.id, classes.class_name, timetable.subject, timetable.start_time, timetable.end_time
            FROM timetable
            JOIN classes ON timetable.class_id = classes.id
            WHERE timetable.class_id=?
            ORDER BY timetable.start_time
        """, (selected_class_id,))
        timetable = c.fetchall()
    conn.close()
    return render_template("timetable.html", classes=classes, timetable=timetable,
                           selected_class_id=int(selected_class_id) if selected_class_id else None)

@app.route("/add_timetable", methods=["POST"])
def add_timetable():
    class_id = request.form["class_id"]
    subject = request.form["subject"]
    start_time = request.form["start_time"]
    end_time = request.form["end_time"]
    conn = sqlite3.connect('attendance.db')
    c = conn.cursor()
    c.execute("INSERT INTO timetable (class_id, subject, start_time, end_time) VALUES (?,?,?,?)",
              (class_id, subject, start_time, end_time))
    conn.commit()
    conn.close()
    return redirect(f"/timetable?class_id={class_id}")

@app.route("/delete_timetable/<int:tid>", methods=["POST"])
def delete_timetable(tid):
    if session.get("role") != "admin":
        return "Unauthorized", 403
    class_id = request.form.get("class_id")
    conn = sqlite3.connect('attendance.db')
    c = conn.cursor()
    c.execute("SELECT subject FROM timetable WHERE id=?", (tid,))
    row = c.fetchone()
    if row:
        subject_to_delete = row[0]
        c.execute("""
            DELETE FROM attendance
            WHERE subject=? AND student_id IN (
                SELECT id FROM students WHERE class_id=?
            )
        """, (subject_to_delete, class_id))
    c.execute("DELETE FROM timetable WHERE id=?", (tid,))
    conn.commit()
    conn.close()
    return redirect(f"/timetable?class_id={class_id}")

@app.route("/edit_timetable/<int:tid>", methods=["GET", "POST"])
def edit_timetable(tid):
    if session.get("role") != "admin":
        return "Unauthorized", 403
    conn = sqlite3.connect('attendance.db')
    c = conn.cursor()
    if request.method == "POST":
        subject = request.form["subject"]
        start_time = request.form["start_time"]
        end_time = request.form["end_time"]
        class_id = request.form["class_id"]
        c.execute("UPDATE timetable SET subject=?, start_time=?, end_time=? WHERE id=?",
                  (subject, start_time, end_time, tid))
        conn.commit()
        conn.close()
        return redirect(f"/timetable?class_id={class_id}")
    else:
        c.execute("SELECT class_id, subject, start_time, end_time FROM timetable WHERE id=?", (tid,))
        row = c.fetchone()
        conn.close()
        if row:
            class_id, subject, start_time, end_time = row
            return render_template("edit_timetable.html", tid=tid, class_id=class_id,
                                   subject=subject, start_time=start_time, end_time=end_time)
    return "Not found", 404

# ---------- ADD STUDENT (dropdown) ----------
@app.route("/add_student_form")
def add_student_form():
    if session.get("role") != "admin":
        return "Unauthorized", 403
    conn = sqlite3.connect('attendance.db')
    c = conn.cursor()
    c.execute("SELECT id, class_name FROM classes ORDER BY class_name")
    classes = c.fetchall()
    conn.close()
    return render_template("add_student.html", classes=classes)

@app.route("/add_student", methods=["POST"])
def add_student():
    if session.get("role") != "admin":
        return "Unauthorized", 403
    usn = request.form["usn"]
    name = request.form["name"]
    dob = request.form["dob"]
    class_id = request.form["class_id"]
    image_path = request.form["image_path"].strip('"').strip("'")
    if not os.path.exists('known_images'):
        os.makedirs('known_images')
    ext = os.path.splitext(image_path)[1]
    dest_path = os.path.join('known_images', f"{usn}{ext}")
    shutil.copyfile(image_path, dest_path)
    encoding = capture_face_encoding(dest_path)
    if encoding is None:
        return "Face not found in image"
    face_blob = pickle.dumps(encoding)
    conn = sqlite3.connect('attendance.db')
    c = conn.cursor()
    c.execute("INSERT INTO students (usn, name, dob, class_id, face_encoding) VALUES (?,?,?,?,?)",
              (usn, name, dob, class_id, face_blob))
    conn.commit()
    conn.close()
    return "Student added successfully"

# ---------- MARK ATTENDANCE (with dropdowns) ----------
@app.route("/mark_attendance", methods=["GET", "POST"])
def mark_attendance():
    if session.get("role") != "admin":
        return "Unauthorized", 403
    conn = sqlite3.connect('attendance.db')
    c = conn.cursor()
    c.execute("SELECT id, class_name FROM classes")
    classes = c.fetchall()
    selected_class_id = request.args.get("class_id")
    subjects = []
    if selected_class_id:
        try:
            cid = int(selected_class_id)
            c.execute("SELECT DISTINCT subject FROM timetable WHERE class_id=?", (cid,))
            subjects = [row[0] for row in c.fetchall()]
        except ValueError:
            pass
    conn.close()
    if request.method == "POST":
        class_id = int(request.form["class_id"])
        subject = request.form["subject"]
        run_live_attendance(class_id, subject)
        return "Attendance process completed"
    return render_template("mark_attendance.html",
                           classes=classes,
                           selected_class_id=int(selected_class_id) if selected_class_id else None,
                           subjects=subjects)

# ---------- ADMIN ATTENDANCE ----------
@app.route("/admin/attendance", methods=["GET", "POST"])
def admin_attendance():
    if session.get("role") != "admin":
        return "Unauthorized", 403
    conn = sqlite3.connect('attendance.db')
    c = conn.cursor()
    if request.method == "POST":
        for key, value in request.form.items():
            if key.startswith("status_"):
                att_id = key.split("_")[1]
                c.execute("UPDATE attendance SET status=? WHERE id=?", (value, att_id))
        conn.commit()
    class_id = request.args.get("class_id")
    subject = request.args.get("subject")
    date = request.args.get("date", datetime.date.today().strftime("%Y-%m-%d"))
    student_id = request.args.get("student_id")
    try:
        class_id_int = int(class_id) if class_id else None
    except:
        class_id_int = None
    c.execute("SELECT id, class_name FROM classes")
    classes = c.fetchall()
    subjects = []
    students_list = []
    attendance_records = []
    if class_id_int:
        c.execute("SELECT DISTINCT subject FROM timetable WHERE class_id=?", (class_id_int,))
        subjects = [s[0] for s in c.fetchall()]
        c.execute("SELECT id, usn, name FROM students WHERE class_id=? ORDER BY name", (class_id_int,))
        students_list = c.fetchall()
        if subject:
            query = """SELECT attendance.id, students.usn, students.name, attendance.status
                       FROM attendance JOIN students ON attendance.student_id = students.id
                       WHERE students.class_id=? AND attendance.subject=? AND attendance.date=?"""
            params = [class_id_int, subject, date]
        else:
            query = """SELECT attendance.id, students.usn, students.name, attendance.subject, attendance.status
                       FROM attendance JOIN students ON attendance.student_id = students.id
                       WHERE students.class_id=? AND attendance.date=?"""
            params = [class_id_int, date]
        if student_id:
            query += " AND students.id=?"
            params.append(student_id)
        query += " ORDER BY students.usn, attendance.subject"
        c.execute(query, params)
        attendance_records = c.fetchall() # Always a list, works for single/multiple records 
    conn.close()
    return render_template("admin_attendance.html",
                           classes=classes, subjects=subjects,
                           students_list=students_list,
                           attendance_records=attendance_records,
                           selected_class=class_id_int,
                           selected_subject=subject,
                           selected_date=date,
                           selected_student=int(student_id) if student_id else None)

@app.route("/delete_attendance/<int:att_id>", methods=["POST"])
def delete_attendance(att_id):
    if session.get("role") != "admin":
        return "Unauthorized", 403
    class_id = request.form.get("class_id")
    subject = request.form.get("subject")
    date = request.form.get("date")
    student_id = request.form.get("student_id")
    conn = sqlite3.connect('attendance.db')
    c = conn.cursor()
    c.execute("DELETE FROM attendance WHERE id=?", (att_id,))
    conn.commit()
    conn.close()
    redir = f"/admin/attendance?class_id={class_id}&subject={subject}&date={date}"
    if student_id:
        redir += f"&student_id={student_id}"
    return redirect(redir)

# ---------- ADMIN STUDENT ATTENDANCE HISTORY ----------
@app.route("/admin/student_attendance_history", methods=["GET", "POST"])
def student_attendance_history():
    if session.get("role") != "admin":
        return "Unauthorized", 403
    conn = sqlite3.connect('attendance.db')
    c = conn.cursor()
    c.execute("SELECT id, class_name FROM classes ORDER BY class_name")
    classes = c.fetchall()
    selected_class_id = request.args.get("class_id") or request.form.get("class_id")
    selected_student_id = request.args.get("student_id") or request.form.get("student_id")
    start_date = request.args.get("start_date") or request.form.get("start_date")
    end_date = request.args.get("end_date") or request.form.get("end_date")
    filtered_students, attendance_records, student_info = [], [], None
    if selected_class_id:
        c.execute("SELECT id, usn, name FROM students WHERE class_id=? ORDER BY name", (selected_class_id,))
        filtered_students = c.fetchall()
    if selected_student_id:
        c.execute("SELECT usn, name FROM students WHERE id=?", (selected_student_id,))
        student_info = c.fetchone()
        query = "SELECT subject, date, status FROM attendance WHERE student_id=?"
        params = [selected_student_id]
        if start_date and end_date:
            query += " AND date BETWEEN ? AND ?"
            params.extend([start_date, end_date])
        elif start_date:
            query += " AND date >= ?"
            params.append(start_date)
        elif end_date:
            query += " AND date <= ?"
            params.append(end_date)
        query += " ORDER BY date DESC"
        c.execute(query, params)
        attendance_records = c.fetchall()
    elif selected_class_id:
        query = """
            SELECT students.usn, students.name, attendance.subject, attendance.date, attendance.status
            FROM attendance
            JOIN students ON attendance.student_id = students.id
            WHERE students.class_id=?
        """
        params = [selected_class_id]
        if start_date and end_date:
            query += " AND attendance.date BETWEEN ? AND ?"
            params.extend([start_date, end_date])
        elif start_date:
            query += " AND attendance.date >= ?"
            params.append(start_date)
        elif end_date:
            query += " AND attendance.date <= ?"
            params.append(end_date)
        query += " ORDER BY attendance.date DESC, students.name ASC"
        c.execute(query, params)
        attendance_records = c.fetchall()
    # Calculate subject-wise attendance statistics
    subject_stats = {}
    for record in attendance_records:
        subject = record[0]
        if subject not in subject_stats:
            subject_stats[subject] = {
                'total': 0,
                'present': 0,
                'absent': 0,
                'percentage': 0
            }
        subject_stats[subject]['total'] += 1
        if record[2] == 'Present':
            subject_stats[subject]['present'] += 1
        else:
            subject_stats[subject]['absent'] += 1
        subject_stats[subject]['percentage'] = round(
            (subject_stats[subject]['present'] / subject_stats[subject]['total'] * 100)
            if subject_stats[subject]['total'] > 0 else 0
        )
    
    # Calculate overall statistics
    total_records = len(attendance_records)
    present_count = sum(subject_stats[subj]['present'] for subj in subject_stats)
    absent_count = total_records - present_count
    attendance_percentage = round((present_count / total_records * 100) if total_records > 0 else 0)
    
    conn.close()
    return render_template("student_attendance_history.html",
                           classes=classes, filtered_students=filtered_students,
                           attendance_records=attendance_records,
                           selected_class_id=int(selected_class_id) if selected_class_id else None,
                           selected_student_id=int(selected_student_id) if selected_student_id else None,
                           student_info=student_info, start_date=start_date, end_date=end_date,
                           total_records=total_records,
                           present_count=present_count,
                           absent_count=absent_count,
                           attendance_percentage=attendance_percentage,
                           subject_stats=subject_stats)

# ---------- OPTIONAL: CSV DOWNLOAD ENDPOINT ----------
@app.route("/admin/download_attendance")
def download_attendance():
    if session.get("role") != "admin":
        return "Unauthorized", 403
    class_id = request.args.get("class_id")
    subject = request.args.get("subject")
    date = request.args.get("date")
    student_id = request.args.get("student_id")
    conn = sqlite3.connect('attendance.db')
    c = conn.cursor()
    query = """SELECT students.usn, students.name, attendance.subject, attendance.date, attendance.status
               FROM attendance
               JOIN students ON attendance.student_id = students.id
               WHERE students.class_id=?"""
    params = [class_id]
    if subject:
        query += " AND attendance.subject=?"
        params.append(subject)
    if date:
        query += " AND attendance.date=?"
        params.append(date)
    if student_id:
        query += " AND students.id=?"
        params.append(student_id)
    query += " ORDER BY attendance.date DESC, students.name"
    c.execute(query, params)
    records = c.fetchall()
    conn.close()
    # create CSV
    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(["USN", "Name", "Subject", "Date", "Status"])
    for rec in records:
        writer.writerow(rec)
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename=attendance_report.csv"
    output.headers["Content-type"] = "text/csv"
    return output

# ---------- STUDENT: Attendance Graph & History ----------
@app.route("/attendance_graph/<subject>")
def attendance_graph(subject):
    if "username" not in session or session["role"] != "student":
        return redirect("/")
    usn = session["username"]
    conn = sqlite3.connect('attendance.db')
    c = conn.cursor()
    c.execute("SELECT id FROM students WHERE usn=?", (usn,))
    student_id = c.fetchone()[0]
    c.execute("""SELECT date, status 
                 FROM attendance 
                 WHERE student_id=? AND subject=?
                 ORDER BY date""", (student_id, subject))
    attendance_records = c.fetchall()
    dates = []
    statuses = []
    for record in attendance_records:
        dates.append(record[0])
        statuses.append(1 if record[1].strip().lower() == "present" else 0)
    conn.close()
    return render_template("attendance_graph.html", 
                          subject=subject, 
                          dates=dates, 
                          statuses=statuses, 
                          records=attendance_records)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(debug=True)
