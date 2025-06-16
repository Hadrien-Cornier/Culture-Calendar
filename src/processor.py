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
    
    def process_events(self, events: List[Dict]) -> List[Dict]:
        """Process and enrich all events"""
        enriched_events = []
        
        for event in events:
            try:
                # Only process screenings for now
                if event.get('type') != 'screening':
                    continue
                
                print(f"Processing: {event['title']}")
                
                # Get movie rating from AI
                ai_rating = self._get_ai_rating(event['title'])
                
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
            Rate the movie "{movie_title}" on a scale of 1-10 and provide a brief summary.
            Consider critical reception, cultural significance, and general appeal.
            Format your response as: RATING: X/10 - Brief summary here
            """
            
            data = {
                'model': 'llama-3.1-sonar-small-128k-online',
                'messages': [
                    {'role': 'user', 'content': prompt}
                ],
                'max_tokens': 200
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
    
    def _parse_ai_response(self, content: str) -> Dict:
        """Parse AI response to extract rating and summary"""
        try:
            # Look for rating pattern like "RATING: 8/10"
            import re
            rating_match = re.search(r'RATING:\s*(\d+)/10', content, re.IGNORECASE)
            
            if rating_match:
                score = int(rating_match.group(1))
                # Extract summary (everything after the rating)
                summary = content[rating_match.end():].strip()
                if summary.startswith('-'):
                    summary = summary[1:].strip()
            else:
                # Fallback: look for any number/10 pattern
                fallback_match = re.search(r'(\d+)/10', content)
                if fallback_match:
                    score = int(fallback_match.group(1))
                    summary = content.strip()
                else:
                    score = 5
                    summary = content.strip()
            
            return {
                'score': max(1, min(10, score)),  # Clamp to 1-10
                'summary': summary[:200]  # Limit summary length
            }
            
        except Exception as e:
            print(f"Error parsing AI response: {e}")
            return {'score': 5, 'summary': content[:200]}
    
    def _calculate_preference_score(self, event: Dict, ai_rating: Dict) -> int:
        """Calculate preference score based on user preferences"""
        score = 0
        
        # Check title, description, and AI summary for preferences
        text_to_check = (
            event.get('title', '') + ' ' +
            event.get('description', '') + ' ' +
            ai_rating.get('summary', '')
        ).lower()
        
        # Add points for matching preferences
        for preference in self.preferences:
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