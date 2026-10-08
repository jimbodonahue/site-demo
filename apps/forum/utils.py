from apps.authentication.models import CustomUser
from apps.exercises.models import Exercise
from .models import Post, Topic


def get_system_user():
    system_user = CustomUser.objects.filter(token="00000000000000000000000000000000").first()
    if not system_user:
        system_user, _ = CustomUser.objects.get_or_create_token_user(
            token="00000000000000000000000000000000"
        )
        system_user.username = "Platform System"
        system_user.save(update_fields=["username"])
    return system_user


RESOURCES_WIKI_TOPICS = [
    (
        "Theory",
        (
            "Useful Resources — Theory\n\n"
            "Share and discover conceptual foundations for data science and computing.\n\n"
            "Starter reading:\n"
            "• Probability & Statistics overview: https://seeing-theory.brown.edu/\n"
            "• Linear Algebra intuition: https://www.3blue1brown.com/topics/linear-algebra\n"
            "• Bias–variance tradeoff notes: https://en.wikipedia.org/wiki/Bias%E2%80%93variance_tradeoff\n\n"
            "Add your favorite theory explainers, textbooks, and lecture notes below."
        ),
    ),
    (
        "Programming",
        (
            "Useful Resources — Programming\n\n"
            "Practical coding references for Python and everyday data work.\n\n"
            "Starter links:\n"
            "• Official Python Documentation: https://docs.python.org/3/\n"
            "• Pandas Documentation: https://pandas.pydata.org/docs/\n"
            "• NumPy User Guide: https://numpy.org/doc/stable/\n"
            "• Real Python tutorials: https://realpython.com/\n\n"
            "Share cheatsheets, patterns, and debugging tips below."
        ),
    ),
    (
        "Machine Learning",
        (
            "Useful Resources — Machine Learning\n\n"
            "Models, evaluation, and applied ML workflows.\n\n"
            "Starter links:\n"
            "• Scikit-Learn User Guide: https://scikit-learn.org/stable/user_guide.html\n"
            "• Google Machine Learning Crash Course: https://developers.google.com/machine-learning/crash-course\n"
            "• Papers With Code: https://paperswithcode.com/\n\n"
            "Post tutorials, notebooks, and model-evaluation tips below."
        ),
    ),
    (
        "Data Analysis",
        (
            "Useful Resources — Data Analysis\n\n"
            "Exploring, cleaning, visualizing, and communicating data findings.\n\n"
            "Starter links:\n"
            "• Matplotlib Tutorials: https://matplotlib.org/stable/tutorials/index.html\n"
            "• Seaborn Tutorial: https://seaborn.pydata.org/tutorial.html\n"
            "• Data cleaning checklist ideas: https://en.wikipedia.org/wiki/Data_cleansing\n\n"
            "Share visualization galleries, EDA workflows, and storytelling examples below."
        ),
    ),
    (
        "Tools & Libraries",
        (
            "Useful Resources — Tools & Libraries\n\n"
            "Development tools, environments, and helpful libraries.\n\n"
            "Starter links:\n"
            "• Jupyter Lab: https://jupyterlab.readthedocs.io/\n"
            "• VS Code Python docs: https://code.visualstudio.com/docs/languages/python\n"
            "• uv package manager: https://docs.astral.sh/uv/\n\n"
            "Recommend editors, CLI tools, and libraries that speed up your workflow."
        ),
    ),
]

COMMUNITY_TOPICS = [
    (
        Topic.SECTION_JOB_MARKET,
        "Job Market Readiness",
        (
            "Job Market Readiness\n\n"
            "Use this space to prepare for internships and data roles.\n\n"
            "Discussion ideas:\n"
            "• Resume and portfolio feedback\n"
            "• Interview practice questions\n"
            "• How to talk about projects and soft skills\n"
            "• What hiring managers look for in junior candidates\n\n"
            "Share opportunities, advice, and questions — help each other get ready."
        ),
    ),
    (
        Topic.SECTION_ACHIEVEMENTS,
        "Celebrate Achievements",
        (
            "Celebrate Achievements\n\n"
            "Finished an exercise? Landed an interview? Finally understood a tricky concept?\n\n"
            "Post your wins here — big or small. Encourage classmates, share what clicked, "
            "and build momentum together.\n\n"
            "Prompt ideas:\n"
            "• “I just completed …”\n"
            "• “Today I finally figured out …”\n"
            "• “I’m proud that I …”"
        ),
    ),
]


def _ensure_topic_with_intro(*, title, section, system_user, intro_content, unique_by_section=False):
    if unique_by_section:
        topic, created = Topic.objects.get_or_create(
            section=section,
            defaults={"title": title, "created_by": system_user},
        )
        if topic.title != title:
            topic.title = title
            topic.save(update_fields=["title"])
    else:
        topic, created = Topic.objects.get_or_create(
            title=title,
            section=section,
            defaults={"created_by": system_user},
        )
    if not topic.posts.exists():
        Post.objects.create(topic=topic, author=system_user, content=intro_content)
    return topic


def ensure_forum_topics():
    """
    Guarantees that:
    1. Useful Resources wiki topics exist (Theory, Programming, ML, etc.).
    2. Job Market Readiness and Celebrate Achievements topics exist.
    3. Every published exercise has an automatically created discussion topic.
    """
    system_user = get_system_user()

    # Retire the legacy single resources thread in favor of the wiki topics.
    legacy = Topic.objects.filter(title="Useful Resources & Learning Materials").first()
    if legacy:
        programming_exists = Topic.objects.filter(
            title="Programming", section=Topic.SECTION_RESOURCES
        ).exclude(pk=legacy.pk).exists()
        legacy.section = Topic.SECTION_RESOURCES
        legacy.title = "Resources Archive" if programming_exists else "Programming"
        legacy.save(update_fields=["section", "title"])

    for title, intro in RESOURCES_WIKI_TOPICS:
        _ensure_topic_with_intro(
            title=title,
            section=Topic.SECTION_RESOURCES,
            system_user=system_user,
            intro_content=intro,
        )

    for section, title, intro in COMMUNITY_TOPICS:
        _ensure_topic_with_intro(
            title=title,
            section=section,
            system_user=system_user,
            intro_content=intro,
            unique_by_section=True,
        )

    published_exercises = Exercise.objects.filter(published=True)
    for exercise in published_exercises:
        Topic.objects.get_or_create(
            exercise=exercise,
            defaults={
                "title": f"Discussion: {exercise.title}",
                "created_by": system_user,
                "section": Topic.SECTION_EXERCISE,
            },
        )

    Topic.objects.filter(exercise__isnull=False).exclude(section=Topic.SECTION_EXERCISE).update(
        section=Topic.SECTION_EXERCISE
    )
