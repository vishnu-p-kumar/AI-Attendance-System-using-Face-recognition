import face_recognition
import cv2
import pickle
import datetime
import sqlite3

def capture_face_encoding(image_path):
    img = face_recognition.load_image_file(image_path)
    encodings = face_recognition.face_encodings(img)
    return encodings[0] if encodings else None

def run_live_attendance(class_id, subject):
    conn = sqlite3.connect('attendance.db')
    c = conn.cursor()
    c.execute("SELECT id, face_encoding, name FROM students WHERE class_id=?", (class_id,))
    students = c.fetchall()

    known_encodings = []
    student_ids = []
    student_names = []
    for sid, encoding_blob, name in students:
        if encoding_blob:
            known_encodings.append(pickle.loads(encoding_blob))
            student_ids.append(sid)
            student_names.append(name)

    present_students = set()
    cam = cv2.VideoCapture(0)
    start_time = datetime.datetime.now()

    while True:
        ret, frame = cam.read()
        if not ret:
            break

        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        face_locations = face_recognition.face_locations(rgb_frame)
        face_encodings = face_recognition.face_encodings(rgb_frame, known_face_locations=face_locations)

        for (top, right, bottom, left), encoding in zip(face_locations, face_encodings):
            matches = face_recognition.compare_faces(known_encodings, encoding, tolerance=0.5)
            name = "Unknown"

            if True in matches:
                idx = matches.index(True)
                sid = student_ids[idx]
                name = student_names[idx]
                present_students.add(sid)

            cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
            cv2.putText(frame, name, (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 0), 2)

        cv2.imshow("Mark Attendance - Press Q to stop", frame)

        if (datetime.datetime.now() - start_time).seconds > 15:
            break
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cam.release()
    cv2.destroyAllWindows()

    date_today = datetime.date.today().strftime("%Y-%m-%d")
    for sid in student_ids:
        status = "Present" if sid in present_students else "Absent"
        c.execute("INSERT INTO attendance (student_id, subject, date, status) VALUES (?,?,?,?)",
                  (sid, subject, date_today, status))

    conn.commit()
    conn.close()
