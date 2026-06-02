# home/management/commands/test_afrisenti.py

from django.core.management.base import BaseCommand
from home.nlp import afrisenti_analyzer

class Command(BaseCommand):
    help = "Test AfriSenti model integration"

    def add_arguments(self, parser):
        parser.add_argument(
            "--text",
            type=str,
            default="Hoteli hii ni chafu kwa kweli",
            help="Text to analyze"
        )
        parser.add_argument(
            "--language",
            type=str,
            default="sw",
            choices=["sw", "en"],
            help="Language of the text"
        )

    def handle(self, *args, **options):
        text = options["text"]
        language = options["language"]
        
        self.stdout.write(f"Testing AfriSenti model with text: {text}")
        self.stdout.write(f"Language: {language}")
        
        label, score, model = afrisenti_analyzer.analyze(text, language)
        
        self.stdout.write(self.style.SUCCESS(f"Result: {label} (score: {score:.4f})"))
        self.stdout.write(f"Model used: {model}")

