"""
Event processor for enriching and rating events
"""

import os
import requests
from typing import List, Dict, Optional
from datetime import datetime
import json
import time
from dotenv import load_dotenv

load_dotenv()

class EventProcessor:
    def __init__(self):
        self.perplexity_api_key = os.getenv('PERPLEXITY_API_KEY')
        self.preferences = self._load_preferences()
        # Separate preference list for literature events
        self.literature_preferences = self._load_literature_preferences()
        self.movie_cache = {}  # Cache AI ratings to avoid reprocessing
    
    def process_events(self, events: List[Dict]) -> List[Dict]:
        """Process and enrich all events"""
        enriched_events = []
        total_events = len(events)
        processed_count = 0
        
        for i, event in enumerate(events, 1):
            try:
                # Process screenings, concerts, and book clubs
                if event.get('type') not in ['screening', 'concert', 'book_club']:
                    continue
                
                # Skip work hours (9am-6pm) on weekdays
                if self._is_during_work_hours(event):
                    print(f"Skipping {event['title']} - during work hours")
                    continue
                
                processed_count += 1
                print(f"Processing ({processed_count}): {event['title']}")
                
                # Get AI rating (with caching)
                event_title = event['title'].upper().strip()
                if event_title in self.movie_cache:
                    print(f"  Using cached rating for {event_title}")
                    ai_rating = self.movie_cache[event_title]
                else:
                    if event.get('type') == 'concert':
                        ai_rating = self._get_classical_rating(event)
                    elif event.get('type') == 'book_club':
                        ai_rating = self._get_book_club_rating(event)
                    else:
                        ai_rating = self._get_ai_rating(event['title'])
                    self.movie_cache[event_title] = ai_rating
                
                # Calculate personal preference score
                preference_score = self._calculate_preference_score(event, ai_rating)
                
                # Add enriched data
                event['ai_rating'] = ai_rating
                event['preference_score'] = preference_score
                event['final_rating'] = self._calculate_final_rating(ai_rating, preference_score)
                event['rating_explanation'] = self._generate_rating_explanation(event, ai_rating, preference_score)
                
                enriched_events.append(event)
                
                # Rate limiting for API calls
                time.sleep(1)
                
            except Exception as e:
                print(f"Error processing event '{event.get('title', 'Unknown')}': {e}")
                # Add event with minimal data
                event['ai_rating'] = {'score': 5, 'summary': 'Unable to rate'}
                event['preference_score'] = 0
                event['final_rating'] = 5
                event['rating_explanation'] = 'Rating unavailable'
                enriched_events.append(event)
        
        return enriched_events
    
    def _load_preferences(self) -> List[str]:
        """Load user preferences from file"""
        preferences = []
        try:
            with open('preferences.txt', 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        preferences.append(line.lower())
        except FileNotFoundError:
            print("Warning: preferences.txt not found")

        return preferences

    def _load_literature_preferences(self) -> List[str]:
        """Load literature-specific preferences from file"""
        preferences = []
        try:
            with open('literature_preferences.txt', 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        preferences.append(line.lower())
        except FileNotFoundError:
            print("Warning: literature_preferences.txt not found")

        return preferences
    
    def _get_ai_rating(self, movie_title: str) -> Dict:
        """Get movie rating and info from Perplexity API"""
        if not self.perplexity_api_key:
            return {'score': 5, 'summary': 'No API key provided'}
        
        try:
            headers = {
                'Authorization': f'Bearer {self.perplexity_api_key}',
                'Content-Type': 'application/json'
            }
            
            prompt = f"""
            Analyze "{movie_title}" with the intellectual rigor of a French cinéaste, focusing purely on artistic excellence, aesthetic beauty, and universal human experiences. Provide a concise, well-structured analysis with the following sections:

            ★ Rating: [X/10] (Integer Only) - Reflecting artistic merit, technical brilliance, and aesthetic achievement. Value films that explore timeless human experiences over those with heavy political messaging.
            🎬 Synopsis: A brief overview focusing on narrative craft, character development, and emotional depth.
            👤 Director: A short bio emphasizing their artistic vision and cinematic technique.
            🎨 Central Themes: The universal human experiences and aesthetic concepts explored, focusing on beauty, truth, love, loss, growth, and other timeless elements.
            🏛️ Cultural Legacy: The film's artistic influence and technical innovations in cinema.

            Evaluate the film's commitment to artistic excellence and sensitivity rather than ideological positions. Appreciate works that transcend political boundaries to explore what makes us fundamentally human.
            """
            
            data = {
                'model': 'llama-3.1-sonar-small-128k-online',
                'messages': [
                    {'role': 'user', 'content': prompt}
                ],
                'max_tokens': 2000
            }
            
            response = requests.post(
                'https://api.perplexity.ai/chat/completions',
                headers=headers,
                json=data,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content']
                return self._parse_ai_response(content)
            else:
                print(f"Perplexity API error: {response.status_code}")
                return {'score': 5, 'summary': 'API error'}
                
        except Exception as e:
            print(f"Error calling Perplexity API: {e}")
            return {'score': 5, 'summary': 'Unable to get rating'}
    
    def _get_classical_rating(self, event: Dict) -> Dict:
        """Get classical music concert rating and analysis from Perplexity API"""
        if not self.perplexity_api_key:
            return {'score': 5, 'summary': 'No API key provided'}
        
        try:
            headers = {
                'Authorization': f'Bearer {self.perplexity_api_key}',
                'Content-Type': 'application/json'
            }
            
            # Extract key information from the event
            concert_title = event.get('title', '')
            program = event.get('program', '')
            composers = event.get('composers', [])
            works = event.get('works', [])
            featured_artist = event.get('featured_artist', '')
            series = event.get('series', '')
            
            # Create detailed concert description for analysis
            concert_description = f"Concert: {concert_title}\nSeries: {series}\nProgram: {program}\nFeatured Artist: {featured_artist}"
            
            prompt = f"""
            Analyze this classical music concert with the intellectual sophistication of a distinguished music critic, focusing on artistic excellence, aesthetic beauty, and the profound human experiences conveyed through classical music. Provide a refined, well-structured analysis with the following sections:

            ★ Rating: [X/10] (Integer Only) - Reflecting artistic significance, performance quality, and aesthetic achievement. Value works that explore timeless human emotions and universal experiences through musical excellence.

            🎼 Program Overview: A sophisticated analysis of the musical works and their narrative significance, focusing on emotional depth, structural brilliance, and artistic craftsmanship.

            👤 Composers & Artists: Brief insights into the composers' artistic vision and the featured performers' interpretive excellence, emphasizing their contribution to the classical tradition.

            🎨 Musical Themes: The universal human experiences and aesthetic concepts explored through this music - beauty, transcendence, passion, melancholy, triumph, and other profound emotions that connect us across time and culture.

            🏛️ Cultural Significance: The lasting impact of these works on classical music tradition, their technical innovations, and their place in the pantheon of great music.

            Concert Details:
            {concert_description}

            Evaluate the concert's commitment to artistic excellence and emotional depth rather than contemporary political messaging. Appreciate works that transcend temporal boundaries to express what makes us fundamentally human through the universal language of music.
            """
            
            data = {
                'model': 'llama-3.1-sonar-small-128k-online',
                'messages': [
                    {'role': 'user', 'content': prompt}
                ],
                'max_tokens': 2000
            }
            
            response = requests.post(
                'https://api.perplexity.ai/chat/completions',
                headers=headers,
                json=data,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content']
                return self._parse_ai_response(content)
            else:
                print(f"Perplexity API error: {response.status_code}")
                return {'score': 5, 'summary': 'API error'}
                
        except Exception as e:
            print(f"Error calling Perplexity API for classical music: {e}")
            return {'score': 5, 'summary': 'Unable to get rating'}
    
    def _get_book_club_rating(self, event: Dict) -> Dict:
        """Get book club discussion rating and analysis from Perplexity API"""
        if not self.perplexity_api_key:
            return {'score': 5, 'summary': 'No API key provided'}
        
        try:
            headers = {
                'Authorization': f'Bearer {self.perplexity_api_key}',
                'Content-Type': 'application/json'
            }
            
            # Extract key information from the event
            book_title = event.get('book', '')
            author = event.get('author', '')
            host = event.get('host', '')
            venue = event.get('venue', '')
            description = event.get('description', '')
            
            # Create detailed book description for analysis
            book_description = f"Book: {book_title} by {author}\nHost: {host}\nVenue: {venue}\nDescription: {description}"
            
            prompt = f"""
            Analyze this book club discussion with the intellectual sophistication of a distinguished literary critic, focusing on artistic excellence, literary merit, and the profound human experiences conveyed through literature. Provide a refined, well-structured analysis with the following sections:

            ★ Rating: [X/10] (Integer Only) - Reflecting literary significance, artistic merit, and the book's contribution to understanding the human condition. Value works that explore timeless themes and universal experiences.

            📚 Literary Overview: A sophisticated analysis of the book's narrative structure, thematic depth, and artistic craftsmanship, focusing on how it illuminates the human experience.

            ✍️ Author & Style: Brief insights into the author's literary vision, writing style, and their place in the literary tradition, emphasizing their contribution to literature.

            🎭 Central Themes: The universal human experiences and philosophical concepts explored through this work - love, identity, mortality, beauty, truth, justice, and other profound themes that connect us across cultures and time.

            📖 Literary Significance: The lasting impact of this work on literature, its innovative techniques, and its place in the canon of important books that expand our understanding of what it means to be human.

            🗣️ Discussion Value: The richness of themes and ideas that make this book particularly rewarding for thoughtful discussion among readers seeking intellectual and emotional engagement.

            Book Club Details:
            {book_description}

            Evaluate the book's commitment to artistic excellence and emotional truth rather than didactic messaging. Appreciate works that transcend their immediate context to express what makes us fundamentally human through the power of storytelling and literary art.
            """
            
            data = {
                'model': 'llama-3.1-sonar-small-128k-online',
                'messages': [
                    {'role': 'user', 'content': prompt}
                ],
                'max_tokens': 2000
            }
            
            response = requests.post(
                'https://api.perplexity.ai/chat/completions',
                headers=headers,
                json=data,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content']
                return self._parse_ai_response(content)
            else:
                print(f"Perplexity API error: {response.status_code}")
                return {'score': 5, 'summary': 'API error'}
                
        except Exception as e:
            print(f"Error calling Perplexity API for book club: {e}")
            return {'score': 5, 'summary': 'Unable to get rating'}
    
    def _parse_ai_response(self, content: str) -> Dict:
        """Parse AI response to extract rating and summary"""
        try:
            import re
            # Look for rating pattern like "★ Rating: 8/10" or "[8/10]" or "3.6/10"
            rating_patterns = [
                r'★\s*Rating:\s*\[?(\d+(?:\.\d+)?)/10\]?',
                r'\[(\d+(?:\.\d+)?)/10\]',
                r'RATING:\s*(\d+(?:\.\d+)?)/10',
                r'(\d+(?:\.\d+)?)/10'
            ]
            
            score = 5  # Default score
            for pattern in rating_patterns:
                rating_match = re.search(pattern, content, re.IGNORECASE)
                if rating_match:
                    score = round(float(rating_match.group(1)))
                    break
            
            # Use the full content as summary for the French cinéaste style
            summary = content.strip()
            
            return {
                'score': max(1, min(10, score)),  # Clamp to 1-10
                'summary': summary  # Keep full summary
            }
            
        except Exception as e:
            print(f"Error parsing AI response: {e}")
            return {'score': 5, 'summary': content[:2000]}
    
    def _calculate_preference_score(self, event: Dict, ai_rating: Dict) -> int:
        """Calculate preference score based on user preferences"""
        score = 0

        # Check title, description, and AI summary for preferences
        text_to_check = (
            event.get('title', '') + ' ' +
            event.get('description', '') + ' ' +
            ai_rating.get('summary', '')
        ).lower()

        # Combine general preferences with literature-specific ones for book clubs
        preferences_to_use = list(self.preferences)
        if event.get('type') == 'book_club':
            preferences_to_use += self.literature_preferences

        # Add points for matching preferences
        for preference in preferences_to_use:
            if preference in text_to_check:
                score += 2
        
        # Bonus for special screenings
        if event.get('is_special_screening'):
            score += 3
        
        return score
    
    def _calculate_final_rating(self, ai_rating: Dict, preference_score: int) -> int:
        """Calculate final rating combining AI and preference scores"""
        base_rating = ai_rating.get('score', 5)
        
        # Apply preference boost (max +3 points)
        boost = min(3, preference_score // 2)
        
        final_rating = min(10, base_rating + boost)
        
        return final_rating
    
    def _generate_rating_explanation(self, event: Dict, ai_rating: Dict, preference_score: int) -> str:
        """Generate explanation for the rating"""
        explanation_parts = []
        
        # AI rating part
        ai_score = ai_rating.get('score', 5)
        explanation_parts.append(f"AI Rating: {ai_score}/10")
        
        # Preference boost
        if preference_score > 0:
            boost = min(3, preference_score // 2)
            explanation_parts.append(f"Personal preference boost: +{boost}")
        
        # Special screening bonus
        if event.get('is_special_screening'):
            explanation_parts.append("✨ Special screening")
        
        # AI summary
        summary = ai_rating.get('summary', '').strip()
        if summary:
            explanation_parts.append(f"Summary: {summary}")
        
        return " | ".join(explanation_parts)
    
    def _is_during_work_hours(self, event: Dict) -> bool:
        """Check if event is during work hours (9am-6pm weekdays)"""
        try:
            # Parse date
            date_str = event.get('date')
            if not date_str:
                return False
            
            event_date = datetime.strptime(date_str, '%Y-%m-%d')
            
            # Skip weekends (Saturday=5, Sunday=6)
            if event_date.weekday() >= 5:
                return False
            
            # Parse time
            time_str = event.get('time', '').strip()
            if not time_str:
                return False
            
            # Extract hour from time string like "2:30 PM"
            import re
            time_match = re.search(r'(\d{1,2}):(\d{2})\s*([AP]M)', time_str.upper())
            if not time_match:
                return False
            
            hour, minute, ampm = time_match.groups()
            hour = int(hour)
            minute = int(minute)
            
            # Convert to 24-hour format
            if ampm == 'PM' and hour != 12:
                hour += 12
            elif ampm == 'AM' and hour == 12:
                hour = 0
            
            # Check if between 9am (9) and 6pm (18)
            event_time_minutes = hour * 60 + minute
            work_start = 9 * 60  # 9:00 AM
            work_end = 18 * 60   # 6:00 PM
            
            return work_start <= event_time_minutes <= work_end
            
        except Exception as e:
            print(f"Error checking work hours for {event.get('title', 'Unknown')}: {e}")
            return False