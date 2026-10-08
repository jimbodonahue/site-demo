def unread_notification_count(request):
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {"unread_notification_count": 0}
    from .models import Notification

    return {
        "unread_notification_count": Notification.objects.filter(
            recipient=request.user,
            is_read=False,
        ).count()
    }
