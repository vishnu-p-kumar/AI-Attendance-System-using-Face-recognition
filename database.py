import sqlite3

def init_db():
    conn = sqlite3.connect('attendance.db')
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS admin (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usn TEXT UNIQUE,
        name TEXT,
        dob TEXT,
        class_id INTEGER,
        face_encoding BLOB
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS classes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        class_name TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS timetable (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        class_id INTEGER,
        subject TEXT,
        start_time TEXT,
        end_time TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER,
        subject TEXT,
        date TEXT,
        status TEXT
    )''')

    # Insert default admin if none exists
    c.execute("SELECT * FROM admin")
    if not c.fetchone():
        c.execute("INSERT INTO admin (username, password) VALUES (?,?)", ("admin", "admin123"))

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
