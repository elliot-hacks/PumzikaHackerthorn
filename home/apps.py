# home/apps.py
from django.apps import AppConfig


class HomeConfig(AppConfig):
    name               = "home"
    verbose_name       = "Review Sentiment & NLP"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        self._register_beat_schedule()
        self._register_admin_urls()

    def _register_beat_schedule(self):
        try:
            from django.conf import settings
            from celery.schedules import crontab
            beat = getattr(settings, "CELERY_BEAT_SCHEDULE", {})
            defaults = {
                "home.bulk_process_home": {
                    "task":     "home.tasks.bulk_process_home",
                    "schedule": crontab(minute="*/15"),   # every 15 min
                    "options":  {"expires": 800},
                },
                "home.build_sentiment_snapshots": {
                    "task":     "home.tasks.build_sentiment_snapshots",
                    "schedule": crontab(hour=0, minute=30),  # 00:30 daily
                    "options":  {"expires": 3_600},
                },
                "home.update_topic_clusters": {
                    "task":     "home.tasks.update_topic_clusters",
                    "schedule": crontab(hour=1, minute=0),   # 01:00 daily
                    "options":  {"expires": 3_600},
                },
                "home.generate_property_insights": {
                    "task":     "home.tasks.generate_property_insights",
                    "schedule": crontab(hour=2, minute=0),   # 02:00 daily
                    "options":  {"expires": 7_200},
                },
            }
            for key, val in defaults.items():
                beat.setdefault(key, val)
            settings.CELERY_BEAT_SCHEDULE = beat
        except ImportError:
            pass
        except Exception:
            pass

    def _register_admin_urls(self):
        """Inject the dashboard and documentation URLs into the admin site."""
        try:
            from django.contrib import admin as dj_admin
            from django.urls import path
            from home.admin import ReviewDashboardAdmin, DocumentationView

            original_get_urls = dj_admin.site.__class__.get_urls

            def patched_get_urls(self_inner):
                custom = [
                    path(
                        "home/dashboard/",
                        dj_admin.site.admin_view(ReviewDashboardAdmin.view),
                        name="home_dashboard",
                    ),
                    path(
                        "home/documentation/",
                        dj_admin.site.admin_view(DocumentationView.view),
                        name="home_documentation",
                    ),
                ]
                return custom + original_get_urls(self_inner)

            dj_admin.site.__class__.get_urls = patched_get_urls
        except Exception:
            pass
