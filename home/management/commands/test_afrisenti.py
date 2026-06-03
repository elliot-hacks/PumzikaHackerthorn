# home/management/commands/test_afrisenti.py

from django.core.management.base import BaseCommand
from home.nlp import afrisenti_analyzer, sentiment_scorer

class Command(BaseCommand):
    help = "Test AfriSenti model and Swahili sentiment analysis"

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
        parser.add_argument(
            "--score",

            type=float,
            default=None,
            help="Reviewer score (1-10) to blend with sentiment"
        )

    def handle(self, *args, **options):
        text = options["text"]
        language = options["language"]
        reviewer_score = options["score"]
        
        self.stdout.write(f"Testing sentiment analysis with text: {text}")
        self.stdout.write(f"Language: {language}")
        if reviewer_score is not None:
            self.stdout.write(f"Reviewer score: {reviewer_score}")
        
        # Test 1: Direct AfriSenti transformer (if available)
        self.stdout.write("\n--- AfriSenti Transformer ---")
        label1, score1, model1 = afrisenti_analyzer.analyze(text, language)
        self.stdout.write(f"Result: {label1} (score: {score1:.4f})")
        self.stdout.write(f"Model: {model1}")
        
        # Test 2: Full sentiment scorer with lexicon fallback
        self.stdout.write("\n--- Full Sentiment Scorer (with fallback) ---")
        label2, score2, model2 = sentiment_scorer.score(text, language, reviewer_score)
        self.stdout.write(self.style.SUCCESS(f"Result: {label2} (score: {score2:.4f})"))
        self.stdout.write(f"Model: {model2}")
        
        # Summary
        self.stdout.write("\n--- Summary ---")
        if model2 == "afrisenti_transformer":
            self.stdout.write(self.style.SUCCESS("✓ Using AfriSenti transformer model"))
        elif model2 == "afrisenti_lexicon":
            self.stdout.write(self.style.WARNING("⚡ Using lexicon fallback (transformer unavailable)"))
        else:
            self.stdout.write(f"Using: {model2}")

