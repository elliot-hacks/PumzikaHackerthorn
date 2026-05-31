# Pumzika Hackerthorn - Review Sentiment & NLP Analysis

A Django-based NLP system for analyzing hospitality reviews in the East African context, featuring sentiment analysis, topic extraction, and AI-powered property insights.

## 🏆 Hackerthon Challenge: Review Sentiment & NLP Analysis

This project addresses the challenge of using NLP to analyze sentiment and extract topics from host/guest reviews to improve service quality in East African rental properties.

### Key Features

- **🤖 Sentiment Analysis**: Hybrid NLP engine with AfriSenti-aware scoring for Swahili reviews and LLM-powered analysis for English
- **🏷️ Topic Extraction**: Automatic discovery of review topics (Cleanliness, Staff, Location, Value, etc.)
- **💡 AI Insights**: LLM-generated narrative insights for properties
- **📊 Analytics Dashboard**: Real-time visualization of sentiment trends and topic distribution
- **⌨️ Command Palette**: Keyboard-driven interface with LLM chat for natural language queries (Ctrl+K)
- **💬 LLM Chat**: Ask questions like "What are the best hotels?" and get intelligent responses with data

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- PostgreSQL (optional, SQLite used by default)
- Redis (for Celery background tasks)
- Groq API key (for LLM-powered features)
- Kaggle Hotel Reviews CSV (optional, for demo data)

### Installation

```bash
# Clone the repository
git clone https://github.com/elliot-hacks/PumzikaHackerthorn.git
cd PumzikaHackerthorn

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Set environment variables
export GROQ_API_KEY="your-groq-api-key"

# Start development server
python manage.py runserver
```

### Importing Kaggle Hotel Reviews Data

If you have the Kaggle 515K Hotel Reviews CSV file:

```bash
# Import a test sample (10 reviews)
python manage.py import_kaggle_hotels --csv-path Hotel_Reviews.csv --limit 10

# Import full dataset (515K reviews)
python manage.py import_kaggle_hotels --csv-path Hotel_Reviews.csv --queue-nlp

# Or import without my script
python manage.py shell -c "from home.admin import ReviewAdmin; from home.models import Review; admin = ReviewAdmin(Review, None); r = Review.objects.first(); print(f'Testing admin display methods:'); print(f'  reviewer_score_display: {admin.reviewer_score_display(r)}'); print(f'  sentiment_badge: {admin.sentiment_badge(r)}'); print('✅ Admin methods work correctly!')" 2>&1

# Import with custom batch size
python manage.py import_kaggle_hotels --csv-path Hotel_Reviews.csv --batch-size 1000 --queue-nlp
```

The `--queue-nlp` flag will automatically queue sentiment analysis and topic extraction for all imported reviews.

### Background Processing (Optional)

```bash
# Start Redis (required for Celery)
redis-server

# Start Celery worker
celery -A PumzikaHackerthorn worker --loglevel=info

# Start Celery Beat (scheduled tasks)
celery -A PumzikaHackerthorn beat --loglevel=info
```

## ⌨️ Command Palette with LLM Chat

The command palette provides quick access to all NLP operations via keyboard shortcuts, plus **LLM-powered natural language chat** for querying your hotel review data.

### Activation
- Press `Ctrl+K` (or `Cmd+K` on Mac) to open the command palette
- Type to search for commands or ask questions
- Use arrow keys to navigate, Enter to execute

### Available Commands

#### Navigation
- `📊 Open Dashboard` - View sentiment analytics
- `📝 View All Reviews` - Browse reviews
- `🏷️ View Topic Clusters` - See discovered topics
- `💡 View Property Insights` - See AI insights
- `📈 View Sentiment Snapshots` - See trends

#### NLP Operations
- `🤖 Analyze Sentiment` - Run sentiment analysis on unprocessed reviews
- `🏷️ Extract Topics` - Extract topics from reviews
- `💡 Generate Insights` - Create AI property insights
- `🔄 Update Topic Clusters` - Rebuild topic aggregates
- `📊 Build Sentiment Snapshots` - Generate daily aggregates

#### System
- `📋 Show System Status` - View processing statistics
- `🔄 Refresh Status` - Update status display

### 💬 LLM Chat - Natural Language Queries

The command palette includes an **LLM-powered chat** feature that understands natural language questions about your hotel review data. Simply type a question and get intelligent responses with data visualizations.

#### Example Questions

| Question | What it returns |
|----------|----------------|
| "What are the best hotels?" | Top 10 hotels ranked by reviewer score |
| "Which hotels have the worst cleanliness?" | Hotels with lowest cleanliness aspect scores |
| "Show me hotels with great staff" | Hotels ranked by staff/service aspect |
| "What do guests complain about most?" | Most common complaint topics from negative reviews |
| "Best value for money hotels" | Hotels ranked by value aspect score |
| "Hotels with noise issues" | Hotels with poor noise scores |
| "Top rated hotels in Amsterdam" | Highest-rated hotels in Amsterdam |
| "Hotels with poor WiFi" | Hotels with low WiFi/connectivity scores |

#### How It Works

1. Type a natural language question in the command palette
2. The system detects it's a question (starts with "what", "which", "how", etc.)
3. The LLM processes your query and queries the database
4. Results are displayed with hotel rankings and scores
5. The AI provides a natural language summary of the findings

#### Quick Suggestions

Click any of these suggested queries when the palette opens:
- "What are the best hotels?"
- "Which hotels have the worst cleanliness?"
- "Show me hotels with great staff"
- "What do guests complain about most?"
- "Best value for money hotels"
- "Hotels with noise issues"
- "Top rated hotels in Amsterdam"
- "Hotels with poor WiFi"

## 📁 Project Structure

```
PumzikaHackerthorn/
├── home/                          # Main NLP app
│   ├── management/commands/       # Django management commands
│   │   ├── analyze_sentiment.py   # Sentiment analysis command
│   │   ├── extract_topics.py      # Topic extraction command
│   │   ├── generate_insights.py   # Insight generation command
│   │   └── nlp_status.py          # Status reporting command
│   ├── static/home/js/
│   │   └── command-palette.js     # Command palette frontend
│   ├── templates/admin/
│   │   └── dashboard.html         # Analytics dashboard
│   ├── models.py                  # Data models
│   ├── nlp.py                     # NLP engine
│   ├── tasks.py                   # Celery tasks
│   ├── views.py                   # API endpoints
│   └── admin.py                   # Unfold admin config
├── PumzikaHackerthorn/
│   ├── settings.py                # Django settings
│   ├── urls.py                    # URL routing
│   └── celery.py                  # Celery config
└── manage.py                      # Django CLI
```

## 🗄️ Data Models

### Review
- Core unit of analysis - one row per guest review
- Stores raw text, computed sentiment, topics, and embeddings
- Supports English, Swahili, and other languages

### TopicCluster
- Discovered topic clusters from review analysis
- Tracks review count, sentiment, and affected properties

### SentimentSnapshot
- Daily aggregate sentiment stats per property
- Pre-computed for fast dashboard rendering

### PropertyInsight
- LLM-generated narrative insights for properties
- Includes strengths, weaknesses, and actionable advice

## 🤖 NLP Engine

### Language Detection
- Lightweight heuristics for Swahili/English detection
- Falls back to langdetect library

### Sentiment Scoring
- **Swahili**: AfriSenti-informed lexicon-based scoring
- **English**: LLM-powered analysis with heuristic fallback
- Blends with reviewer scores when available

### Topic Extraction
- LLM-based topic and key phrase extraction
- TF-IDF keyword fallback for offline operation
- 8 hospitality aspects: Cleanliness, Staff, Location, Value, Amenities, WiFi, Food, Noise

### Aspect Analysis
- Scores each aspect 0.0-1.0 based on sentiment-weighted keyword presence
- Contextual analysis within 60-character windows

## 📊 Dashboard

Access the analytics dashboard at `/admin/home/dashboard/`

### Visualizations
- Sentiment distribution (donut chart)
- Language breakdown (English vs Swahili)
- Sentiment trends over time (line chart)
- Top topics by volume (bar chart)
- Aspect satisfaction scores (radar chart)
- Properties with most negative reviews

### Status Bar
Real-time display of:
- Processing rate (processed/total reviews)
- Swahili review count
- Topic cluster count
- Property insight coverage

## ⚡ Management Commands

```bash
# Analyze sentiment for unprocessed reviews
python manage.py analyze_sentiment --batch-size 100 --async

# Extract topics from reviews
python manage.py extract_topics --update-clusters --async

# Generate property insights
python manage.py generate_insights --all --async

# Show system status
python manage.py nlp_status --brief
python manage.py nlp_status --json
```

## 🔧 Configuration

### Unfold Admin Settings
```python
UNFOLD = {
    "SITE_HEADER": "Pumzika Hackerthorn",
    "SITE_TITLE": "NLP Review Analytics",
    "COMMAND": {
        "search_models": ["home.Review", "home.PropertyInsight", "home.TopicCluster"],
        "show_history": False,
    },
}
```

### Celery Beat Schedule
- Every 15 min: Bulk process unprocessed reviews
- Daily 00:30: Build sentiment snapshots
- Daily 01:00: Update topic clusters
- Daily 02:00: Generate property insights

## 📈 Judging Criteria Alignment

### NLP Precision (30%)
- Hybrid sentiment scoring with AfriSenti-aware Swahili handling
- Multi-stage topic extraction with LLM and keyword fallback
- Aspect-level sentiment analysis for granular insights

### Technical Implementation (25%)
- Clean architecture with separate NLP, tasks, and API layers
- Celery for scalable background processing
- Django Unfold for professional admin interface

### Usability (25%)
- Command palette for keyboard-driven workflow
- Real-time dashboard with Chart.js visualizations
- Quick action buttons for common operations

### Innovation (20%)
- East African context with Swahili language support
- LLM-powered narrative insights for properties
- Command palette integration for admin efficiency

## 🛠️ Tech Stack

- **Backend**: Django 6.0, Celery
- **Admin**: Django Unfold
- **NLP**: Custom engine with multi-model LLM integration
- **LLM Providers**: Groq (primary), Mistral AI, OpenRouter (failover)
- **Database**: SQLite (dev), PostgreSQL (prod)
- **Cache/Broker**: Redis
- **Frontend**: Chart.js, Vanilla JS
- **Charts**: Chart.js

## 🌍 East African Context Adaptation

This system is specifically designed for the East African hospitality market:

### Cultural Context
- **Swahili Language Support**: AfriSenti-informed sentiment lexicon for Swahili reviews
- **Local Hospitality Norms**: Understanding of "pole pole" (slowly) culture, "hakuna matata" expectations
- **Regional Aspects**: Safety, cultural experiences, safari arrangements, infrastructure considerations

### Multi-Model Architecture
The system uses a weighted load-balancing approach across multiple LLM providers:

| Provider | Model | Weight | Purpose |
|----------|-------|--------|---------|
| Groq | Llama 3.3 70B | 50% | Primary - fast, reliable |
| Mistral AI | Mistral Large | 33% | Secondary - European context |
| OpenRouter | Llama 3 70B | 17% | Tertiary - backup |

### API Configuration
```bash
# Set up multiple providers for reliability
export GROQ_API_KEY="your-groq-key"
export MISTRAL_API_KEY="your-mistral-key"  
export OPENROUTER_API_KEY="your-openrouter-key"
```

The system automatically fails over if one provider is unavailable, ensuring continuous operation.

## 📄 License

MIT License - Built for the Pumzika Hackerthorn

---

**Built with ❤️ for East African hospitality analytics**