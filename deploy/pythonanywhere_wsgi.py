"""
Paste this into the WSGI file linked from the PythonAnywhere Web tab
(/var/www/YOURUSERNAME_pythonanywhere_com_wsgi.py).

Replace YOURUSERNAME and the project folder name if yours differs.
Delete any Flask/Bottle sample code above the Django section first.
"""

import os
import sys

# Folder that contains manage.py (repo root after git clone)
project_home = "/home/YOURUSERNAME/site-demo"
if project_home not in sys.path:
    sys.path.insert(0, project_home)

os.environ["DJANGO_SETTINGS_MODULE"] = "project_core.settings"

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()
