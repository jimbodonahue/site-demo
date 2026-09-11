# Implementation Plan for Course Platform

## Overview of Django Apps

| App Name | Responsibility | Primary Models | Typical Views |
|---|---|---|---|
| `courses` | Manages courses and their metadata. | `Course` (title, description, author, etc.) | `CourseListView`, `CourseDetailView` |
| `exercises` | Handles exercises belonging to a course. Can be a separate app or a sub‑module of `courses`. | `Exercise` (title, content, order, course FK) | `ExerciseListView`, `ExerciseDetailView` |
| `forum` | Community discussion for each course/exercise. Could use `django‑contrib‑comments` or a custom implementation. | `Thread`, `Post` (linked to `Course` or `Exercise`) | `ThreadListView`, `ThreadDetailView`, `PostCreateView` |
| `accounts` (optional) | User registration / authentication. | `User` (Django default) | `LoginView`, `LogoutView`, `SignupView` |

## File Structure (relative to project root)

```
myproject/
├─ manage.py
├─ myproject/                # Project settings package
│   ├─ __init__.py
│   ├─ settings.py          # Add new apps to INSTALLED_APPS
│   ├─ urls.py              # Include app URL configs
│   └─ wsgi.py
├─ courses/
│   ├─ __init__.py
│   ├─ admin.py
│   ├─ apps.py
│   ├─ models.py            # Course model
│   ├─ urls.py              # /courses/ …
│   ├─ views.py             # List & detail views
│   └─ templates/courses/   # course_* .html files
├─ exercises/                # optional separate app
│   ├─ __init__.py
│   ├─ admin.py
│   ├─ apps.py
│   ├─ models.py            # Exercise model (FK → Course)
│   ├─ urls.py               # /exercises/ …
│   ├─ views.py              # List & detail views
│   └─ templates/exercises/  # exercise_* .html files
├─ forum/
│   ├─ __init__.py
│   ├─ admin.py
│   ├─ apps.py
│   ├─ models.py            # Thread, Post models (generic FK to Course/Exercise)
│   ├─ urls.py              # /forum/ …
│   ├─ views.py             # Thread list/detail, new post
│   └─ templates/forum/     # forum_*.html files
├─ accounts/ (optional)
│   └─ …
└─ templates/base.html      # Base layout used by all apps
```

## Detailed Step‑by‑Step Instructions

### 1. Create the apps
```bash
python manage.py startapp courses
python manage.py startapp exercises   # if you prefer a separate app
python manage.py startapp forum
# optional
python manage.py startapp accounts
```

### 2. Register apps in `myproject/settings.py`
```python
INSTALLED_APPS = [
    # default apps …
    'courses',
    'exercises',   # or omit if exercises live in `courses`
    'forum',
    'accounts',   # optional
    # third‑party apps (e.g., django‑contrib‑comments)
]
```

### 3. Define models
- **courses/models.py**
  ```python
  class Course(models.Model):
      title = models.CharField(max_length=200)
      description = models.TextField()
      owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
      created_at = models.DateTimeField(auto_now_add=True)
  ```
- **exercises/models.py** (or inside `courses/models.py` as a related model)
  ```python
  class Exercise(models.Model):
      course = models.ForeignKey('courses.Course', on_delete=models.CASCADE, related_name='exercises')
      title = models.CharField(max_length=200)
      content = models.TextField()
      order = models.PositiveIntegerField()
  ```
- **forum/models.py** (generic relations for flexibility)
  ```python
  from django.contrib.contenttypes.fields import GenericForeignKey
  from django.contrib.contenttypes.models import ContentType

  class Thread(models.Model):
      title = models.CharField(max_length=200)
      creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
      created_at = models.DateTimeField(auto_now_add=True)
      # Generic relation – a thread can belong to a Course or an Exercise
      content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
      object_id = models.PositiveIntegerField()
      content_object = GenericForeignKey('content_type', 'object_id')

  class Post(models.Model):
      thread = models.ForeignKey(Thread, on_delete=models.CASCADE, related_name='posts')
      author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
      body = models.TextField()
      created_at = models.DateTimeField(auto_now_add=True)
  ```

### 4. Create migrations and apply
```bash
python manage.py makemigrations
python manage.py migrate
```

### 5. Build URLs
- **myproject/urls.py**
  ```python
  from django.urls import include, path
  urlpatterns = [
      path('admin/', admin.site.urls),
      path('courses/', include('courses.urls')),
      path('exercises/', include('exercises.urls')),
      path('forum/', include('forum.urls')),
      path('accounts/', include('accounts.urls')),
  ]
  ```
- Each app gets a `urls.py` with its own patterns (list, detail, create, etc.).

### 6. Implement Views (class‑based generic views are sufficient)
- **courses/views.py** – `ListView` for all courses, `DetailView` showing course details and a list of its exercises.
- **exercises/views.py** – `ListView` filtered by `course_id`, `DetailView` for a single exercise.
- **forum/views.py** – `ThreadListView` (filtered by the parent object), `ThreadDetailView` showing posts, `PostCreateView`.
- Use `LoginRequiredMixin` where editing/creating is needed.

### 7. Templates
Create a shared `base.html` with navigation links:
- Courses → `/courses/`
- Forum → `/forum/`
- Account actions (login/logout)

Each view renders a template that extends `base.html`. Keep templates inside the app’s `templates/<app_name>/` folder and add the app’s template directory to `DIRS` in `TEMPLATES` setting if using a global path.

### 8. Add Forum Integration
Two approaches:
1. **Custom** – as outlined in the models above (generic FK). Provides full control.
2. **Third‑party** – install `django-contrib-comments` and configure it for `Course` and `Exercise` objects.
   ```bash
   pip install django-contrib-comments
   ```
   Add `'django_comments'` to `INSTALLED_APPS` and use `{% render_comment_list for object %}` in templates.

Choose the method that best fits the learning goals of the course.

### 9. Optional: Student Resource Sharing
Add a simple `Resource` model inside the `forum` app (or a dedicated `resources` app) that stores file uploads or external URLs, linked to a `Course`.

### 10. Testing & Styling
- Write unit tests for model relationships and view permissions.
- Apply a modern CSS framework (e.g., Tailwind or Bootstrap) to make the UI pleasant.
- Verify that the navigation flows: Course list → Course detail → Exercise list → Exercise detail → Forum threads related to that exercise.

### 11. Deployment
- Configure static files, database (PostgreSQL recommended), and a production WSGI server (Gunicorn + Nginx).
- Set `ALLOWED_HOSTS`, enable HTTPS, and configure the forum’s moderation settings.

---

**Resulting file location:** `IMPLEMENTATION_PLAN.md` at the root of the artifact directory.

You can now open this markdown file to review the complete plan.
