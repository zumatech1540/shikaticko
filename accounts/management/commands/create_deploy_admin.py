
import os

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = "Create or promote the production administrator."

    def handle(self, *args, **options):
        User = get_user_model()

        username = os.environ.get("DJANGO_ADMIN_USERNAME")
        email = os.environ.get("DJANGO_ADMIN_EMAIL")
        password = os.environ.get("DJANGO_ADMIN_PASSWORD")

        if not all([username, email, password]):
            raise CommandError(
                "Set DJANGO_ADMIN_USERNAME, "
                "DJANGO_ADMIN_EMAIL and DJANGO_ADMIN_PASSWORD."
            )

        user = User.objects.filter(username=username).first()

        if user is None:
            user = User.objects.create_superuser(
                username=username,
                email=email,
                password=password,
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Administrator '{username}' created successfully."
                )
            )
        else:
            user.is_staff = True
            user.is_superuser = True
            user.is_active = True
            user.save()

            self.stdout.write(
                self.style.SUCCESS(
                    f"Administrator '{username}' verified and promoted."
                )
            )
