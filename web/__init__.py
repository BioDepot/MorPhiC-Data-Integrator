from flask import Flask
from flask_wtf import CSRFProtect

#configuration
app = Flask(__name__)
app.config.from_object('config.Config')
app.secret_key = 'secret_key'
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False
csrf = CSRFProtect(app)


from web import routes