import collections
import datetime
import os
import re
import urlparse

from authomatic.adapters import WerkzeugAdapter
from authomatic import Authomatic
import flask
import flask_sqlalchemy

from auth_config import AUTH_CONFIG
import osgb


ON_OPENSHIFT = 'OPENSHIFT_APP_NAME' in os.environ

if ON_OPENSHIFT:
    OPENID_PATH = os.environ['OPENSHIFT_TMP_DIR']
else:
    OPENID_PATH = '/tmp'


MAP_API_KEY = os.environ['MAP_API_KEY']


authomatic = Authomatic(AUTH_CONFIG, os.environ['AUTHOMATIC_SECRET'],
                        report_errors=False)


AUTH_SESSION_KEY = 'authomatic:github:state'

app = flask.Flask(__name__)
app.config.from_pyfile('app.cfg')
app.config['SECRET_KEY'] = os.environ['FLASK_SECRET_KEY']

db = flask_sqlalchemy.SQLAlchemy(app)


@app.route('/login')
def login():
    template_args = default_template_values()
    return flask.render_template('login', **template_args)


@app.route('/auth/<provider_name>', methods=['GET', 'POST'])
def auth_provider(provider_name):
    response = flask.make_response()
    result = authomatic.login(WerkzeugAdapter(flask.request, response),
                              provider_name, session=flask.session,
                              session_saver=lambda: app.save_session(
                                  flask.session, response))
    if result:
        # Check for membership of the AshburtonH3 organisation.
        response = result.provider.access('https://api.github.com/user/orgs')
        if (response.status != 200 or
                'AshburtonH3' not in [org['login'] for org in response.data]):
            flask.session.pop(AUTH_SESSION_KEY, None)
        return flask.redirect('/admin')
    return response


@app.route('/logout')
def logout():
    flask.session.pop(AUTH_SESSION_KEY, None)
    return flask.redirect('/')


class Newsflash(db.Model):
    __tablename__ = 'newsflashes'
    id = db.Column(db.Integer, primary_key=True)
    words = db.Column(db.Text())


class Hash(db.Model):
    __tablename__ = 'hashes'
    its_when = db.Column(db.Date, primary_key=True)
    its_where = db.Column(db.String(200))
    on_down = db.Column(db.String(200))
    who = db.Column(db.String(100))
    what = db.Column(db.String(100))
    lat = db.Column(db.Float())
    lon = db.Column(db.Float())
    easting = db.Column(db.Integer())
    northing = db.Column(db.Integer())
    words = db.Column(db.Text())

    def lat_lon(self):
        if self.lat and self.lon:
            return '{}, {}'.format(self.lat, self.lon)
        elif self.easting and self.northing:
            lat, lon = osgb.osgb_to_wgs84_lat_long(self.easting, self.northing)
            return '{}, {}'.format(lat, lon)
        return ''

    def human_readable_when(self):
        its_when = self.its_when
        if its_when.weekday() == 1:  # aka. Tuesday
            when = '{}<sup>{}</sup> {} {}'.format(
                its_when.day,
                {1: 'st', 2: 'nd', 3: 'rd'}.get(its_when.day % 10, 'th'),
                its_when.strftime('%B'), its_when.year)
        else:
            fmt = '{}<sup>{}</sup> {} {} <span class="weekday">({})<span>'
            when = fmt.format(
                its_when.day,
                {1: 'st', 2: 'nd', 3: 'rd'}.get(its_when.day % 10, 'th'),
                its_when.strftime('%B'), its_when.year,
                its_when.strftime('%A'))
        return when

    def land_ranger(self):
        return osgb.osgb_to_land_ranger(self.easting, self.northing)

    def streetmap_url(self):
        fmt = 'http://www.streetmap.co.uk/map.srf?X={}&Y={}&A=Y&Z=115'
        return fmt.format(self.easting, self.northing)

    def short_words(self, cutoff=60):
        if self.words:
            words = (self.words or '')[:cutoff]
            match = re.search(r'\w+$', words)
            if match:
                words = words[:match.start(0)]
            words = words.rstrip()
        else:
            words = ''
        return words

    def paragraphs(self):
        # Check for double-"newline" paragraphs.
        paragraphs = re.split(r'\r?\n\r?\n', self.words)
        if len(paragraphs) == 1:
            # Assume single-"newline" paragraphs.
            paragraphs = re.split(r'\r?\n', self.words)
        else:
            # Convert single-"newline"s to <br>
            paragraphs = ['<br>'.join(re.split(r'\r?\n', paragraph))
                          for paragraph in paragraphs]
        return paragraphs


MenuItem = collections.namedtuple('MenuItem', ('title', 'url'))


MENU_ITEMS = [
    MenuItem('Home', '/'),
    MenuItem('Diary', '/diary'),
    MenuItem('Archive', '/archive'),
    MenuItem('Where', '/map'),
    MenuItem('Contacts', '/contacts')
]


def menu(current_url):
    menu_items = [menu_item._asdict() for menu_item in MENU_ITEMS]
    for menu_item in menu_items:
        if menu_item['url'] == current_url:
            menu_item['selected'] = True
    return menu_items


def default_template_values():
    if is_admin():
        auth_url = '/logout'
        auth_action = 'Log out'
    else:
        auth_url = 'https://ah3-rhattersley.rhcloud.com/login'
        auth_action = 'Log in'

    template_values = {
        'menu_items': menu(flask.request.path),
        'is_admin': is_admin(),
        'auth_url': auth_url,
        'auth_action': auth_action,
    }
    return template_values


def first_tuesday():
    # Find the first Tuesday on or after Today
    date = datetime.date.today()
    if date.weekday() == 0:
        date += datetime.timedelta(1)
    elif date.weekday() > 1:
        date += datetime.timedelta(8 - date.weekday())
    assert date.weekday() == 1  # aka. Tuesday
    return date


@app.route('/')
def index():
    hashes = Hash.query.order_by(Hash.its_when).filter(
        Hash.its_when >= datetime.date.today())
    hash_ = hashes.first()
    template_args = default_template_values()
    if hash_ is not None:
        template_args['hash'] = hash_
    newsflash = _newsflash()
    if newsflash.words:
        template_args['newsflash'] = newsflash
    template_args['map_api_key'] = MAP_API_KEY
    return flask.render_template('index', **template_args)


@app.route('/diary')
def diary():
    query = Hash.query
    query = query.filter(Hash.its_when >= datetime.date.today())
    hashes = query.order_by(Hash.its_when).limit(10).all()
    template_args = default_template_values()
    template_args['hashes'] = hashes
    return flask.render_template('diary', **template_args)


@app.route('/archive')
def archive():
    query = Hash.query
    query = query.filter(Hash.its_when < datetime.date.today())
    hashes = query.order_by(Hash.its_when.desc()).limit(10).all()
    template_args = default_template_values()
    template_args['hashes'] = hashes
    return flask.render_template('archive', **template_args)


@app.route('/words/<date>')
def words(date):
    hash_ = _hash_from_date(date)
    template_args = default_template_values()
    template_args['hash'] = hash_
    return flask.render_template('words', **template_args)


@app.route('/contacts')
def contacts():
    template_args = default_template_values()
    return flask.render_template('contacts', **template_args)


@app.route('/map')
def heat_map():
    query = Hash.query
    hashes = query.filter(Hash.lat != None, Hash.lon != None).all()
    template_args = default_template_values()
    template_args['map_api_key'] = MAP_API_KEY
    template_args['hashes'] = hashes
    return flask.render_template('map', **template_args)


def is_admin():
    return AUTH_SESSION_KEY in flask.session


def assert_admin():
    if not is_admin():
        flask.abort(404)


@app.route('/admin')
def admin():
    assert_admin()
    its_when = first_tuesday()

    hashes = []
    for i in range(10):
        hash_ = _hash_from_date(its_when)
        hashes.append(hash_)
        its_when += datetime.timedelta(7)

    template_args = default_template_values()
    template_args['hashes'] = hashes
    newsflash = _newsflash()
    if newsflash.words:
        template_args['newsflash'] = newsflash
    return flask.render_template('admin', **template_args)


def _hash_from_date(its_when):
    if not isinstance(its_when, datetime.date):
        its_when = datetime.date(*map(int, its_when.split('-')))
    assert its_when.weekday() == 1  # aka. Tuesday
    hash_ = Hash.query.filter_by(its_when=its_when).first()
    if hash_ is None:
        hash_ = Hash(its_when=its_when, its_where='', on_down='', who='',
                     what='', words='')
        db.session.add(hash_)
    else:
        hash_.its_where = hash_.its_where or ''
        hash_.on_down = hash_.on_down or ''
        hash_.who = hash_.who or ''
        hash_.what = hash_.what or ''
        hash_.words = hash_.words or ''
    return hash_


def decode_google_maps_url(url):
    # e.g. https://maps.google.co.uk/maps?q=53.22248,-4.183502&
    #       ll=53.216082,-4.185169&spn=0.005017,0.013937&num=1&t=m&z=17
    result = None
    url = urlparse.urlparse(url)
    if url.scheme in ('http', 'https') and \
       url.netloc.startswith('maps.google.'):
        arguments = urlparse.parse_qs(url.query)
        ll = arguments.get('ll')
        if ll and len(ll) == 1:
            bits = ll[0].split(',')
            if len(bits) == 2:
                lat, lon = bits
                try:
                    result = (float(lat), float(lon))
                except ValueError:
                    pass
    return result


def decode_streetmap_url(url):
    result = None
    url = urlparse.urlparse(url)
    if url.scheme in ('http', 'https') and \
       url.netloc.endswith('streetmap.co.uk'):
        arguments = urlparse.parse_qs(url.query)
        x = arguments.get('x', [])
        y = arguments.get('y', [])
        if len(x) == 1 and len(y) == 1 and x[0].isdigit() and y[0].isdigit():
            result = int(x[0]), int(y[0])
    return result


@app.route('/admin/edit/<date>', methods=['GET', 'POST'])
def edit(date):
    assert_admin()
    hash_ = _hash_from_date(date)
    if flask.request.method == 'GET':
        template_args = default_template_values()
        template_args['hash'] = hash_
        return flask.render_template('edit', **template_args)
    else:
        hash_.its_where = flask.request.form.get('where')
        hash_.on_down = flask.request.form.get('on_down')
        who = flask.request.form.get('who').split(',')
        who = [w.strip() for w in who]
        hash_.who = ', '.join(who)
        hash_.what = flask.request.form.get('what')
        #lat_lon_src = flask.request.form.get('lat_lon')
        #lat_lon = decode_google_maps_url(lat_lon_src)
        #if lat_lon:
        #    hash_.lat, hash_.lon = lat_lon
        #else:
        #    bits = lat_lon_src.split(',')
        #    if len(bits) == 2:
        #        try:
        #            hash_.lat = float(bits[0])
        #        except ValueError:
        #            pass
        #        try:
        #            hash_.lon = float(bits[1])
        #        except ValueError:
        #            pass
        grid_ref = flask.request.form.get('grid_ref')
        x_y = decode_streetmap_url(grid_ref)
        if x_y:
            hash_.easting, hash_.northing = x_y
        else:
            # TODO: Nicer error reporting
            assert (len(grid_ref) == 0 or osgb.is_osgb(grid_ref) or
                    osgb.is_land_ranger(grid_ref))
            if ',' in grid_ref:
                hash_.easting, hash_.northing = map(int, grid_ref.split(','))
        db.session.commit()
        return flask.redirect('/admin')


@app.route('/admin/words/<date>', methods=['GET', 'POST'])
def admin_words(date):
    assert_admin()
    hash_ = _hash_from_date(date)
    if flask.request.method == 'GET':
        template_args = default_template_values()
        template_args['hash'] = hash_
        return flask.render_template('edit_words', **template_args)
    else:
        hash_.words = flask.request.form.get('words')
        db.session.commit()
        return flask.redirect('/words/' + date)


def _newsflash():
    newsflash = Newsflash.query.first()
    if newsflash is None:
        newsflash = Newsflash(words='')
        db.session.add(newsflash)
    else:
        newsflash.words = newsflash.words or ''
    return newsflash


@app.route('/admin/newsflash', methods=['GET', 'POST'])
def admin_newsflash():
    assert_admin()
    newsflash = _newsflash()
    if flask.request.method == 'GET':
        template_args = default_template_values()
        template_args['newsflash'] = newsflash
        return flask.render_template('edit_newsflash', **template_args)
    else:
        newsflash.words = flask.request.form.get('words')
        db.session.commit()
        return flask.redirect('/admin')


@app.route('/index.html')
def index_html():
    return flask.redirect('/')


if __name__ == '__main__':
    db.create_all()
    app.run(debug=True)
