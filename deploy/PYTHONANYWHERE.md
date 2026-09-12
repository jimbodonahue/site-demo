# Deploy on PythonAnywhere

## 1. Create the web app

1. Web → **Add a new web app** → **Manual configuration** (not the Django wizard).
2. Choose **Python 3.12** or newer (required for Django 6).
3. Note your site URL: `https://YOURUSERNAME.pythonanywhere.com`.

## 2. Clone and virtualenv

In a Bash console:

```bash
cd ~
git clone https://github.com/jimbodonahue/site-demo.git
cd site-demo

python3.12 -m venv ~/.virtualenvs/site-demo
source ~/.virtualenvs/site-demo/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 3. Environment file

```bash
cp .env.example .env
nano .env   # set DJANGO_SECRET_KEY, YOURUSERNAME in ALLOWED_HOSTS / CSRF / CORS
```

## 4. Database and static files

```bash
source ~/.virtualenvs/site-demo/bin/activate
cd ~/site-demo
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser   # optional
```

## 5. Web tab settings

- **Source code**: `/home/YOURUSERNAME/site-demo`
- **Working directory**: `/home/YOURUSERNAME/site-demo`
- **Virtualenv**: `/home/YOURUSERNAME/.virtualenvs/site-demo`
- **WSGI file**: replace contents with `deploy/pythonanywhere_wsgi.py` (edit `YOURUSERNAME`)

Optional static/media mappings (WhiteNoise already serves `/static/`):

- URL `/media/` → Directory `/home/YOURUSERNAME/site-demo/media`

## 6. Reload

Click **Reload** on the Web tab. If it fails, open the **Error log**.
