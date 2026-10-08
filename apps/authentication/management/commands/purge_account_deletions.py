from django.core.management.base import BaseCommand

from apps.authentication.deletion import process_due_account_deletions


class Command(BaseCommand):
    help = (
        "Delete accounts whose deletion requests are past the 48-hour grace period "
        "and still pending."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=100,
            help="Maximum number of due requests to process (default: 100).",
        )

    def handle(self, *args, **options):
        limit = max(1, int(options["limit"]))
        completed = process_due_account_deletions(limit=limit)
        self.stdout.write(self.style.SUCCESS(f"Purged {completed} account(s)."))
