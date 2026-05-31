"""
URL configuration for home app command palette integration.
"""
from django.urls import path
from home import views

app_name = "home"

urlpatterns = [
    # Command palette API endpoint
    path(
        "api/command-palette/",
        views.command_palette_api,
        name="command_palette_api",
    ),
    # LLM chat API endpoint for natural language queries
    path(
        "api/chat/",
        views.chat_api,
        name="chat_api",
    ),
    # Enhanced dashboard with command palette
    path(
        "dashboard/",
        views.dashboard_with_commands,
        name="dashboard",
    ),
]
