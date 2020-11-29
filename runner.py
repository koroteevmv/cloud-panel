from app import db, app

db.create_all()

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=False)
