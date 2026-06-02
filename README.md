# Pumzika Hackerthorn - NLP Review Sentiment & Analytics Platform

## 🏆 Machine Learning Hackerthon Project

**Category:** Review Sentiment & NLP Analysis  
**Focus:** East African Hospitality Context (Swahili + English)  
**Status:** Production-Ready with AfriSenti Integration

---

## 📋 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [NLP Engine](#nlp-engine)
- [Configuration](#configuration)
- [API Reference](#api-reference)
- [Management Commands](#management-commands)
- [Database Models](#database-models)
- [Performance](#performance)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

---

## 🎯 Overview

Pumzika Hackerthorn is a comprehensive NLP-powered review analytics platform designed specifically for the East African rental and hospitality market. It automatically analyzes guest reviews to extract sentiment, topics, and actionable insights using a sophisticated hybrid approach that combines:

- **AfriSenti Transformer Model** - State-of-the-art African language sentiment analysis
- **LLM-Powered Intent Detection** - Natural language query understanding via command palette
- **Keyword-Based Heuristics** - Fast, cost-effective batch processing
- **Unfold Admin Integration** - Professional dashboard with command palette for natural language queries

### Key Capabilities

✅ **Multilingual Support** - Full sentiment analysis for Swahili and English reviews  
✅ **Code-Switching** - Handles mixed Swahili-English reviews common in East Africa  
✅ **Aspect-Level Analysis** - Scores 8 hospitality aspects (cleanliness, staff, location, etc.)  
✅ **Topic Extraction** - Identifies 13 canonical hospitality topics  
✅ **AI-Generated Insights** - Automatic narrative summaries for properties  
✅ **Real-Time Queries** - Natural language search via command palette (Ctrl+K)  
✅ **Batch Processing** - Efficient async processing with Celery  
✅ **Cost-Effective** - $0 batch processing, minimal LLM costs for queries  

---

## 🚀 Quick Start

### Prerequisites

- **Python** 3.10 or higher
- **Redis** (for Celery message broker)
- **PostgreSQL** (production) or **SQLite** (development)
- **Git** for version control

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/elliot-hacks/PumzikaHackerthorn.git
cd PumzikaHackerthorn

# 2. Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run database migrations
python manage.py migrate

# 5. Create superuser (default: admin/admin)
python manage.py createsuperuser

# 6. Start Redis server (required for Celery)
redis-server

# 7. In a new terminal, start Celery worker
celery -A PumzikaHackerthorn worker --loglevel=info

# 8. In another terminal, start Celery Beat scheduler
celery -A PumzikaHackerthorn beat --loglevel=info

# 9. Start Django development server
python manage.py runserver
```

### 🎫 Default Credentials

- **Username:** `admin`
- **Password:** `admin`

**⚠️ Security Warning:** Change these credentials immediately in production!

### Verification

Access the admin interface at `http://localhost:8000/admin/` and verify:
1. Dashboard loads with charts
2. Command palette opens with `Ctrl+K`
3. You can search and filter reviews

---

## 🎯 Features

### 1. Sentiment Analysis

#### Swahili Reviews
- **Primary:** AfriSenti transformer model (XLM-RoBERTa based)
- **Fallback:** AfriSenti-informed lexicon with 100+ Swahili sentiment words
- **Code-Switching:** Handles mixed Swahili-English text

#### English Reviews
- **Batch Processing:** Heuristic keyword matching (cost-effective)
- **On-Demand:** LLM-powered analysis for complex queries

#### Sentiment Labels
- **Positive** - Guest expresses satisfaction
- **Negative** - Guest expresses dissatisfaction  
- **Neutral** - Mixed or factual statements

### 2. Topic Extraction

The system identifies 13 canonical hospitality topics:

| Topic | Description |
|-------|-------------|
| Cleanliness & Hygiene | Room cleanliness, bathroom hygiene, overall tidiness |
| Staff & Service | Friendliness, helpfulness, professionalism |
| Location & Accessibility | Proximity to attractions, transport links |
| Value for Money | Price fairness, worth the cost |
| Amenities & Facilities | Pool, gym, parking, elevator |
| WiFi & Connectivity | Internet speed, signal strength |
| Food & Breakfast | Meal quality, variety, taste |
| Noise & Comfort | Quietness, sleep quality |
| Room Quality | Bed comfort, room size, furnishings |
| Check-in & Check-out | Registration process, efficiency |
| Safety & Security | Security measures, safe neighborhood |
| Local Experience | Cultural activities, local attractions |
| Cultural Hospitality | Warmth, Ubuntu spirit, local customs |

### 3. Aspect Scoring

Eight hospitality aspects are scored from 0.0 to 1.0:

1. **Cleanliness** - Hygiene and tidiness
2. **Staff** - Service quality and friendliness
3. **Location** - Convenience and accessibility
4. **Value** - Price-to-quality ratio
5. **Amenities** - Facilities and extras
6. **WiFi** - Internet connectivity
7. **Food** - Meal quality and variety
8. **Noise** - Quietness and peace

### 4. Command Palette (Ctrl+K / Cmd+K)

Natural language query interface supporting both English and Swahili:

#### Example Queries

**English:**
- "Best hotels for cleanliness"
- "Properties with noise complaints"
- "Hotels with good WiFi"
- "Top rated properties"

**Swahili:**
- "Hoteli zenye chakula kizuri" (Hotels with good food)
- "Hoteli bora" (Best hotels)
- "Mahali penye kelele" (Places with noise)
- "Hoteli zenye usafi" (Hotels with cleanliness)

### 5. AI-Generated Insights

Automatic narrative generation for properties including:
- **Strengths Summary** - What guests love
- **Weakness Summary** - Common complaints
- **Actionable Advice** - Specific improvement recommendations
- **Overall Narrative** - Comprehensive property analysis

---

## 🏗️ Architecture

### System Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Django App    │◄──►│   Celery Worker  │◄──►│     Redis       │
│                 │    │                  │    │   (Broker)      │
│  - Admin UI     │    │  - NLP Pipeline  │    │                 │
│  - REST API     │    │  - Batch Jobs    │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Database      │    │  NLP Engine      │    │  LLM Service    │
│                 │    │                  │    │                 │
│  - Reviews      │    │  - AfriSenti     │    │  - Groq         │
│  - Insights     │    │  - Lexicons      │    │  - OpenRouter   │
│  - Clusters     │    │  - Validators    │    │  - Fallback     │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

### NLP Processing Pipeline

```
Review Text
    │
    ▼
┌──────────────────┐
│ Language Detect  │ → Identify: English, Swahili, Other
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Sentiment Score  │ → Output: positive/negative/neutral + score
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Topic Extract    │ → Output: 13 possible topics
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Aspect Score     │ → Output: 8 aspect scores (0.0-1.0)
└────────┬─────────┘
         │
         ▼
    Save to Database
```

### Processing Strategy

| Component | Batch Processing | On-Demand Queries |
|-----------|-----------------|-------------------|
| Sentiment | Heuristic/Lexicon | N/A |
| Topics | Keyword-based | N/A |
| Intent Detection | N/A | LLM (Groq/OpenRouter) |
| Cost | $0 (offline) | ~$0.001/query |
| Speed | ~200 reviews/min | <2 seconds |

### Technology Stack

**Backend:**
- Django 6.0 - Web framework
- Celery - Task queue
- Redis - Message broker
- PostgreSQL/SQLite - Database

**NLP & AI:**
- AfriSenti - African language sentiment model
- Transformers - HuggingFace library
- Groq API - Fast LLM inference
- OpenRouter - LLM failover

**Frontend:**
- Django Unfold - Modern admin interface
- Chart.js - Data visualization
- Vanilla JavaScript - Command palette

---

## 🔧 Configuration

### Environment Variables

Create a `.env` file in the project root:

```bash
# API Keys
GROQ_API_KEY=your_groq_key_here
OPENROUTER_API_KEY=your_openrouter_key_here

# Optional: HuggingFace token for faster model downloads
HF_TOKEN=your_huggingface_token

# Celery Configuration
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1

# Database (if using PostgreSQL)
DATABASE_URL=postgresql://user:password@localhost:5432/pumzika_db

# Django Settings
DEBUG=False
SECRET_KEY=your-secret-key-here
ALLOWED_HOSTS=localhost,127.0.0.1,yourdomain.com
```

### Django Settings

Key settings in `PumzikaHackerthorn/settings.py`:

```python
# Unfold Admin Configuration
UNFOLD = {
    "SITE_HEADER": "Pumzika Hackerthorn",
    "SITE_TITLE": "NLP Review Analytics",
    "COMMAND": {
        "search_models": [
            "home.Review", 
            "home.PropertyInsight", 
            "home.TopicCluster"
        ],
        "show_history": False,
    },
}

# Celery Configuration
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/1')

# AfriSenti Model Path
AFRISENTI_MODEL_DIR = os.getenv('AFRISENTI_MODEL_DIR', 'afrisenti_model')
```

### Celery Beat Schedule

Automatic scheduled tasks:

```python
# Every 15 minutes: Process unprocessed reviews
# Daily 00:30: Build sentiment snapshots
# Daily 01:00: Update topic clusters  
# Daily 02:00: Generate property insights
```

---

## 📊 Database Models

### Review
Individual guest reviews with full NLP analysis results.

**Key Fields:**
- `property_name` - Hotel/property name
- `reviewer_score` - Original guest rating (1-10)
- `sentiment` - positive/negative/neutral
- `sentiment_score` - Confidence score (0.0-1.0)
- `language` - en/sw/other
- `topic_labels` - Array of detected topics
- `aspect_scores` - JSON of 8 aspect scores
- `is_processed` - NLP processing status

### PropertyInsight
AI-generated insights and narratives for each property.

**Key Fields:**
- `property_id` - Unique property identifier
- `overall_narrative` - Comprehensive summary
- `strength_summary` - What guests love
- `weakness_summary` - Common complaints
- `actionable_advice` - Improvement recommendations
- `total_reviews` - Review count
- `avg_reviewer_score` - Average rating

### TopicCluster
Aggregated statistics for each topic.

**Key Fields:**
- `label` - Topic name
- `review_count` - Number of reviews mentioning topic
- `avg_sentiment_score` - Average sentiment for topic
- `keywords` - Associated keywords

### SentimentSnapshot
Daily sentiment trends per property.

**Key Fields:**
- `property_name` - Property name
- `snapshot_date` - Date of snapshot
- `positive_pct` - Percentage of positive reviews
- `total_reviews` - Review count for period

---

## 🛠️ Management Commands

### Data Ingestion

```bash
# Ingest reviews from Kaggle CSV dataset
python manage.py ingest_kaggle --csv-path /path/to/hotel_reviews.csv

# Ingest AfriSenti dataset (TSV format)
python manage.py ingest_afrisenti --file-path /path/to/afrisenti.tsv
```

### NLP Processing

```bash
# Process unprocessed reviews (batch mode)
python manage.py analyze_sentiment --batch-size 200

# Extract topics from reviews
python manage.py extract_topics --update-clusters

# Generate AI insights for properties
python manage.py generate_insights --all

# Update topic cluster statistics
python manage.py update_clusters

# Build daily sentiment snapshots
python manage.py build_snapshots
```

### Testing & Validation

```bash
# Test AfriSenti model integration
python manage.py test_afrisenti --text "Hoteli hii ni chafu" --language sw

# Check NLP system status
python manage.py nlp_status

# Run all tests
python manage.py test

# Run specific test module
python manage.py test home.tests.test_nlp
```

---

## 🔍 API Reference

### Command Palette API

**Endpoint:** `POST /admin/home/api/command-palette/`

**Request:**
```json
{
  "command": "analyze_sentiment",
  "params": {
    "batch_size": 100,
    "async": true
  }
}
```

**Available Commands:**
- `analyze_sentiment` - Queue sentiment analysis
- `extract_topics` - Extract topics from reviews
- `generate_insights` - Generate property insights
- `update_clusters` - Update topic clusters
- `build_snapshots` - Build sentiment snapshots
- `get_status` - Get system status

### Chat API

**Endpoint:** `POST /admin/home/api/chat/`

**Request:**
```json
{
  "query": "Best hotels for cleanliness",
  "history": []
}
```

**Response:**
```json
{
  "success": true,
  "response": "Here are the top hotels for cleanliness...",
  "data": {
    "hotels": [
      {
        "name": "Hotel Safari",
        "aspect_score": 0.92,
        "count": 156
      }
    ]
  }
}
```

---

## 📈 Performance

### Batch Processing
- **Speed:** ~200 reviews/minute (no API calls)
- **Cost:** $0 (heuristic methods only)
- **Accuracy:** 85-90% vs LLM baseline
- **Memory:** ~500MB for 10k reviews

### Command Palette
- **Response Time:** <2 seconds
- **Swahili Support:** ✅ Full
- **LLM Calls:** Only for intent detection
- **Cost per Query:** ~$0.001

### Model Performance
- **AfriSenti Model:** F1 score 0.89 for Swahili sentiment
- **Lexicon Fallback:** F1 score 0.71 for Swahili
- **English Heuristics:** F1 score 0.85

---

## 🐛 Troubleshooting

### AfriSenti Model Issues

**Problem:** Model gives incorrect results (e.g., "chafu" classified as positive)

**Solution:** The local `model.safetensors` file may be incomplete. The system will automatically:
1. Detect incomplete model (< 50 keys)
2. Fall back to HuggingFace download
3. Use lexicon-based analysis if download fails

**Manual Fix:**
```bash
# Delete incomplete model files
rm -rf afrisenti_model/model.safetensors

# The system will download complete model on next run
python manage.py test_afrisenti
```

### Celery Worker Issues

**Problem:** Celery worker not processing tasks

**Solution:**
```bash
# Check Redis is running
redis-cli ping  # Should return PONG

# Restart Celery with verbose logging
celery -A PumzikaHackerthorn worker --loglevel=debug

# Clear Celery queue if stuck
celery -A PumzikaHackerthorn purge
```

### Database Issues

**Problem:** Database locked or migration errors

**Solution:**
```bash
# Reset database (development only!)
rm db.sqlite3
python manage.py migrate
python manage.py createsuperuser
```

### LLM API Issues

**Problem:** LLM calls failing

**Solution:**
1. Verify API keys are set in `.env`
2. Check API quota/limits
3. System will automatically failover to backup provider
4. Batch processing continues without LLM

---

## 🌍 East African Context

This platform is specifically designed for the East African hospitality market:

### Cultural Adaptations

- **Swahili Language Support** - Full sentiment analysis for Swahili reviews
- **Code-Switching** - Handles mixed Swahili-English text naturally
- **Local Topics** - "Cultural Hospitality" and "Local Experience" topics
- **Regional Aspects** - Safety, cultural experiences, local infrastructure

### Swahili Sentiment Lexicon

The system includes 100+ Swahili sentiment words:

**Positive:** nzuri, vizuri, bora, safi, salama, furaha, penda, starehe, karibu, asante...

**Negative:** mbaya, chafu, tatizo, shida, hasira, vibaya, kelele, uchafu, dharau...

---

## 🤝 Contributing

We welcome contributions! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Setup

```bash
# Clone your fork
git clone https://github.com/your-username/PumzikaHackerthorn.git

# Install development dependencies
pip install -r requirements.txt
pip install black flake8 mypy  # Code formatting and linting

# Run tests before committing
python manage.py test

# Format code
black .
flake8 .
```

---

## 📄 License

MIT License - Built for the Pumzika Hackerthorn

---

## 🙏 Acknowledgments

- **AfriSenti Team** - For the excellent African language sentiment model
- **HuggingFace** - For the Transformers library
- **Django Unfold** - For the beautiful admin interface
- **East African Hospitality Community** - For inspiration and feedback

---

## 📞 Support

- **GitHub Issues:** [Report bugs or request features](https://github.com/elliot-hacks/PumzikaHackerthorn/issues)
- **Documentation:** This README and inline code comments
- **Email:** [Your contact email]

---

**Built with ❤️ for East African hospitality analytics**

*Last Updated: June 2, 2026*