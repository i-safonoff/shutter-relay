"""Creates the bucket and its CORS policy if they don't exist. Not a
migration -- S3 has no schema Django's migration framework understands --
but the same idea: idempotent, safe to run on every deploy.
"""

from django.core.management.base import BaseCommand

from apps.gallery import storage


class Command(BaseCommand):
    help = "Create the S3 bucket and CORS policy if they don't already exist"

    def handle(self, *args, **options):
        storage.ensure_bucket()
        self.stdout.write(self.style.SUCCESS("bucket ready"))
