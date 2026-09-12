from datetime import date
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///lab_tracker.db'
app.config['SECRET_KEY'] = 'dev-secret-key-change-me'
db = SQLAlchemy(app)

STATUS_NOT_STARTED = 'not_started'
STATUS_IN_PROGRESS = 'in_progress'
STATUS_DONE = 'done'

STATUS_LABELS = {
    STATUS_NOT_STARTED: 'Не начато',
    STATUS_IN_PROGRESS: 'На проверке',
    STATUS_DONE: 'Сдано',
}


# ---------- МОДЕЛИ ----------

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(150), nullable=False)
    group_name = db.Column(db.String(30), nullable=False)

    completions = db.relationship('Completion', backref='student',
                                   cascade='all, delete-orphan')

    def progress(self):
        total = len(self.completions)
        done = len([c for c in self.completions if c.status == STATUS_DONE])
        return done, total


class Discipline(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)

    labs = db.relationship('LabWork', backref='discipline',
                            cascade='all, delete-orphan')


class LabWork(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    discipline_id = db.Column(db.Integer, db.ForeignKey('discipline.id'), nullable=False)
    number = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(200), nullable=False)
    max_score = db.Column(db.Integer, default=5)

    completions = db.relationship('Completion', backref='lab_work',
                                   cascade='all, delete-orphan')


class Completion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    lab_work_id = db.Column(db.Integer, db.ForeignKey('lab_work.id'), nullable=False)
    status = db.Column(db.String(20), default=STATUS_NOT_STARTED)
    submitted_on = db.Column(db.Date, nullable=True)
    score = db.Column(db.Integer, nullable=True)

    __table_args__ = (
        db.UniqueConstraint('student_id', 'lab_work_id', name='uq_student_lab'),
    )


def ensure_completions_exist():
    """Гарантирует, что для каждой пары (студент, лаб. работа) есть запись учёта."""
    students = Student.query.all()
    labs = LabWork.query.all()
    existing = {(c.student_id, c.lab_work_id) for c in Completion.query.all()}
    to_add = []
    for s in students:
        for l in labs:
            if (s.id, l.id) not in existing:
                to_add.append(Completion(student_id=s.id, lab_work_id=l.id,
                                          status=STATUS_NOT_STARTED))
    if to_add:
        db.session.bulk_save_objects(to_add)
        db.session.commit()


# ---------- ГЛАВНАЯ / СТАТИСТИКА ----------

@app.route('/')
def index():
    ensure_completions_exist()
    students = Student.query.order_by(Student.group_name, Student.full_name).all()
    labs_count = LabWork.query.count()
    disciplines_count = Discipline.query.count()

    stats = []
    for s in students:
        done, total = s.progress()
        percent = round(done / total * 100) if total else 0
        stats.append({'student': s, 'done': done, 'total': total, 'percent': percent})

    return render_template('index.html', stats=stats,
                            labs_count=labs_count,
                            disciplines_count=disciplines_count,
                            students_count=len(students))


# ---------- СТУДЕНТЫ ----------

@app.route('/students')
def students_list():
    students = Student.query.order_by(Student.group_name, Student.full_name).all()
    return render_template('students.html', students=students)


@app.route('/students/new', methods=['GET', 'POST'])
def student_new():
    if request.method == 'POST':
        s = Student(full_name=request.form['full_name'].strip(),
                    group_name=request.form['group_name'].strip())
        db.session.add(s)
        db.session.commit()
        ensure_completions_exist()
        flash('Студент добавлен', 'success')
        return redirect(url_for('students_list'))
    return render_template('student_form.html', student=None)


@app.route('/students/<int:student_id>/edit', methods=['GET', 'POST'])
def student_edit(student_id):
    s = Student.query.get_or_404(student_id)
    if request.method == 'POST':
        s.full_name = request.form['full_name'].strip()
        s.group_name = request.form['group_name'].strip()
        db.session.commit()
        flash('Данные студента обновлены', 'success')
        return redirect(url_for('students_list'))
    return render_template('student_form.html', student=s)


@app.route('/students/<int:student_id>/delete', methods=['POST'])
def student_delete(student_id):
    s = Student.query.get_or_404(student_id)
    db.session.delete(s)
    db.session.commit()
    flash('Студент удалён', 'success')
    return redirect(url_for('students_list'))


@app.route('/students/<int:student_id>')
def student_detail(student_id):
    s = Student.query.get_or_404(student_id)
    ensure_completions_exist()
    completions = (Completion.query.filter_by(student_id=student_id)
                   .join(LabWork).join(Discipline)
                   .order_by(Discipline.name, LabWork.number).all())
    return render_template('student_detail.html', student=s,
                            completions=completions, statuses=STATUS_LABELS)


# ---------- ДИСЦИПЛИНЫ ----------

@app.route('/disciplines')
def disciplines_list():
    disciplines = Discipline.query.order_by(Discipline.name).all()
    return render_template('disciplines.html', disciplines=disciplines)


@app.route('/disciplines/new', methods=['GET', 'POST'])
def discipline_new():
    if request.method == 'POST':
        d = Discipline(name=request.form['name'].strip())
        db.session.add(d)
        db.session.commit()
        flash('Дисциплина добавлена', 'success')
        return redirect(url_for('disciplines_list'))
    return render_template('discipline_form.html', discipline=None)


@app.route('/disciplines/<int:discipline_id>/delete', methods=['POST'])
def discipline_delete(discipline_id):
    d = Discipline.query.get_or_404(discipline_id)
    db.session.delete(d)
    db.session.commit()
    flash('Дисциплина удалена', 'success')
    return redirect(url_for('disciplines_list'))


# ---------- ЛАБОРАТОРНЫЕ РАБОТЫ ----------

@app.route('/labs')
def labs_list():
    labs = LabWork.query.join(Discipline).order_by(Discipline.name, LabWork.number).all()
    return render_template('labs.html', labs=labs)


@app.route('/labs/new', methods=['GET', 'POST'])
def lab_new():
    disciplines = Discipline.query.order_by(Discipline.name).all()
    if request.method == 'POST':
        l = LabWork(discipline_id=request.form['discipline_id'],
                    number=int(request.form['number']),
                    title=request.form['title'].strip(),
                    max_score=int(request.form['max_score'] or 5))
        db.session.add(l)
        db.session.commit()
        ensure_completions_exist()
        flash('Лабораторная работа добавлена', 'success')
        return redirect(url_for('labs_list'))
    return render_template('lab_form.html', disciplines=disciplines, lab=None)


@app.route('/labs/<int:lab_id>/delete', methods=['POST'])
def lab_delete(lab_id):
    l = LabWork.query.get_or_404(lab_id)
    db.session.delete(l)
    db.session.commit()
    flash('Лабораторная работа удалена', 'success')
    return redirect(url_for('labs_list'))


# ---------- УЧЁТ ВЫПОЛНЕНИЯ ----------

@app.route('/tracking', methods=['GET', 'POST'])
def tracking():
    ensure_completions_exist()

    if request.method == 'POST':
        completion_id = request.form['completion_id']
        c = Completion.query.get_or_404(completion_id)
        c.status = request.form['status']
        if c.status == STATUS_DONE:
            c.submitted_on = date.today()
            score = request.form.get('score')
            c.score = int(score) if score else None
        else:
            c.submitted_on = None
            c.score = None
        db.session.commit()
        flash('Статус обновлён', 'success')
        return redirect(url_for('tracking', discipline_id=request.args.get('discipline_id', '')))

    discipline_id = request.args.get('discipline_id', type=int)
    disciplines = Discipline.query.order_by(Discipline.name).all()

    labs_query = LabWork.query
    if discipline_id:
        labs_query = labs_query.filter_by(discipline_id=discipline_id)
    labs = labs_query.order_by(LabWork.number).all()

    students = Student.query.order_by(Student.group_name, Student.full_name).all()

    completions_map = {}
    for c in Completion.query.all():
        completions_map[(c.student_id, c.lab_work_id)] = c

    return render_template('tracking.html', students=students, labs=labs,
                            disciplines=disciplines, discipline_id=discipline_id,
                            completions_map=completions_map, statuses=STATUS_LABELS)


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)