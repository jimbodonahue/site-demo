from datetime import date, timedelta

from django.utils import timezone

from .models import ChallengeWeek, Contest


def iso_week_for(day: date | None = None) -> tuple[int, int]:
    day = day or timezone.localdate()
    iso = day.isocalendar()
    return iso.year, iso.week


def week_date_bounds(iso_year: int, iso_week: int) -> tuple[date, date]:
    starts_on = date.fromisocalendar(iso_year, iso_week, 1)
    ends_on = date.fromisocalendar(iso_year, iso_week, 7)
    return starts_on, ends_on


def ensure_week(iso_year: int | None = None, iso_week: int | None = None) -> ChallengeWeek:
    if iso_year is None or iso_week is None:
        iso_year, iso_week = iso_week_for()
    starts_on, ends_on = week_date_bounds(iso_year, iso_week)
    week, _created = ChallengeWeek.objects.get_or_create(
        iso_year=iso_year,
        iso_week=iso_week,
        defaults={"starts_on": starts_on, "ends_on": ends_on},
    )
    for kind, _label in Contest.KIND_CHOICES:
        Contest.objects.get_or_create(week=week, kind=kind)
    return week


def ensure_current_week() -> ChallengeWeek:
    return ensure_week()


def recent_weeks(limit: int = 8) -> list[ChallengeWeek]:
    """Ensure the current week exists, then return recent weeks newest-first."""
    ensure_current_week()
    weeks = list(ChallengeWeek.objects.all()[:limit])
    if len(weeks) < limit:
        current_year, current_week = iso_week_for()
        # Backfill a few prior ISO weeks so visitors can browse history.
        cursor = date.fromisocalendar(current_year, current_week, 1)
        existing = {(w.iso_year, w.iso_week) for w in weeks}
        while len(existing) < limit:
            cursor = cursor - timedelta(days=7)
            year, week_num = cursor.isocalendar()[0], cursor.isocalendar()[1]
            if (year, week_num) in existing:
                continue
            ensure_week(year, week_num)
            existing.add((year, week_num))
        weeks = list(ChallengeWeek.objects.all()[:limit])
    return weeks
